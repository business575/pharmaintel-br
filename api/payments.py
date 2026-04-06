"""
api/payments.py
===============
PharmaIntel BR — Backend de Pagamentos Stripe (FastAPI)

Planos
------
  Starter    R$ 299/mês  → 1 user,  5 NCMs,  sem IA
  Pro        R$ 699/mês  → 3 users, ilimitado NCMs, IA 100 queries/mês
  Enterprise R$ 1.599/mês → 10 users, ilimitado, IA ilimitada, API, white-label
  Extra seat R$ 99/mês (add-on por usuário adicional)

Endpoints
---------
  POST /payments/checkout         → cria Stripe Checkout Session
  POST /payments/webhook          → recebe eventos Stripe (HMAC-validado)
  GET  /payments/subscription     → status da assinatura da empresa autenticada
  POST /payments/portal           → Customer Portal (gerenciar cartão/plano)
  GET  /payments/usage            → consumo atual (AI queries, seats)
  POST /payments/add-seats        → adiciona seats extras via Stripe
  POST /payments/cancel           → agenda cancelamento ao fim do período

Execução
--------
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import stripe
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import get_current_user, _sub_dict, decode_token_safe
from database.crud import (
    activate_subscription,
    add_extra_seats,
    cancel_subscription,
    get_company_by_stripe_customer,
    get_company_users,
    get_subscription,
    get_subscription_by_stripe_id,
    get_usage_count,
    increment_ai_usage,
    log_usage,
    update_subscription_status,
    TIER_DEFAULTS,
)
from database.models import User, get_db, init_db

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stripe config
# ---------------------------------------------------------------------------
stripe.api_key  = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
BASE_URL        = os.getenv("APP_BASE_URL", "http://localhost:8523")

PRICE_IDS = {
    "starter":    os.getenv("STRIPE_PRICE_STARTER",    ""),
    "pro":        os.getenv("STRIPE_PRICE_PRO",        ""),
    "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE", ""),
    "extra_seat": os.getenv("STRIPE_PRICE_EXTRA_SEAT", ""),
}

STRIPE_CONFIGURED = bool(stripe.api_key and not stripe.api_key.startswith("sk_live_your"))

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/payments", tags=["Payments"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    plan: str                    # starter | pro | enterprise
    extra_seats: int = 0


class AddSeatsRequest(BaseModel):
    seats: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stripe_required():
    if not STRIPE_CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail="Stripe não configurado. Adicione STRIPE_SECRET_KEY no .env"
        )


def _price_required(plan: str):
    pid = PRICE_IDS.get(plan, "")
    if not pid or pid.startswith("price_your"):
        raise HTTPException(
            status_code=503,
            detail=f"Price ID do plano '{plan}' não configurado. Execute stripe_products.py"
        )
    return pid


def _get_or_create_stripe_customer(company, email: str) -> str:
    """Retorna stripe_customer_id existente ou cria novo."""
    if company.stripe_customer_id:
        return company.stripe_customer_id
    customer = stripe.Customer.create(
        email=email,
        name=company.name,
        metadata={"company_id": str(company.id), "slug": company.slug},
    )
    return customer.id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/checkout")
def create_checkout(
    req: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cria sessão Stripe Checkout para o plano escolhido."""
    _stripe_required()

    plan = req.plan.lower()
    if plan not in ("starter", "pro", "enterprise"):
        raise HTTPException(400, f"Plano inválido: {plan}")

    price_id = _price_required(plan)
    company  = current_user.company

    try:
        customer_id = _get_or_create_stripe_customer(company, current_user.email)
        if not company.stripe_customer_id:
            company.stripe_customer_id = customer_id
            db.commit()

        line_items = [{"price": price_id, "quantity": 1}]

        # Extra seats como add-on
        if req.extra_seats > 0 and PRICE_IDS.get("extra_seat"):
            line_items.append({
                "price": PRICE_IDS["extra_seat"],
                "quantity": req.extra_seats,
            })

        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=line_items,
            mode="subscription",
            success_url=f"{BASE_URL}?checkout=success",
            cancel_url=f"{BASE_URL}?checkout=canceled",
            subscription_data={
                "metadata": {
                    "company_id":  str(company.id),
                    "plan":        plan,
                    "extra_seats": str(req.extra_seats),
                }
            },
            metadata={
                "company_id":  str(company.id),
                "plan":        plan,
                "extra_seats": str(req.extra_seats),
            },
            locale="pt-BR",
            allow_promotion_codes=True,
        )

        log_usage(db, company.id, "checkout_started",
                  current_user.id, {"plan": plan})
        db.commit()

        return {"checkout_url": session.url, "session_id": session.id}

    except stripe.StripeError as e:
        logger.error("Stripe error: %s", e)
        raise HTTPException(502, str(e))


@router.get("/subscription")
def get_my_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna status detalhado da assinatura da empresa autenticada."""
    sub = get_subscription(db, current_user.company_id)
    if not sub:
        return {"tier": "none", "status": "none"}

    from database.crud import count_active_users
    used_seats = count_active_users(db, current_user.company_id)

    return {
        **_sub_dict(sub),
        "seats_used": used_seats,
        "company_name": current_user.company.name,
    }


@router.get("/usage")
def get_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna métricas de uso do mês atual."""
    from datetime import timedelta
    now   = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    sub = get_subscription(db, current_user.company_id)
    cid = current_user.company_id

    return {
        "period_start": month_start.isoformat(),
        "ai_queries": {
            "used":    sub.ai_queries_used if sub else 0,
            "limit":   sub.ai_queries_limit if sub else 0,
            "remaining": (
                max(0, sub.ai_queries_limit - sub.ai_queries_used)
                if sub and sub.ai_queries_limit != -1
                else -1
            ),
        },
        "api_calls":  get_usage_count(db, cid, "api_call",  since=month_start),
        "etl_runs":   get_usage_count(db, cid, "etl_run",   since=month_start),
        "exports":    get_usage_count(db, cid, "export",    since=month_start),
    }


@router.post("/portal")
def create_portal(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cria sessão do Stripe Customer Portal para gerenciar assinatura."""
    _stripe_required()

    company     = current_user.company
    customer_id = company.stripe_customer_id

    if not customer_id:
        customers = stripe.Customer.list(email=current_user.email, limit=1)
        if not customers.data:
            raise HTTPException(404, "Nenhuma assinatura Stripe encontrada.")
        customer_id = customers.data[0].id

    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=BASE_URL,
        )
        return {"portal_url": portal.url}
    except stripe.StripeError as e:
        raise HTTPException(502, str(e))


@router.post("/add-seats")
def add_seats(
    req: AddSeatsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adiciona seats extras via Stripe (cobrança proporcional)."""
    _stripe_required()
    if req.seats < 1:
        raise HTTPException(400, "Número de seats deve ser >= 1")

    price_id = _price_required("extra_seat")
    sub      = get_subscription(db, current_user.company_id)
    if not sub or not sub.is_active:
        raise HTTPException(402, "Sem assinatura ativa.")

    try:
        # Adiciona item ao subscription existente
        stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
        existing_items = {item["price"]["id"]: item["id"] for item in stripe_sub["items"]["data"]}

        if price_id in existing_items:
            stripe.SubscriptionItem.modify(
                existing_items[price_id],
                quantity=sub.extra_seats + req.seats,
            )
        else:
            stripe.SubscriptionItem.create(
                subscription=sub.stripe_subscription_id,
                price=price_id,
                quantity=req.seats,
            )

        add_extra_seats(db, current_user.company_id, req.seats)
        db.commit()
        return {"message": f"{req.seats} seat(s) adicionado(s).", "total_seats": sub.total_seats}

    except stripe.StripeError as e:
        raise HTTPException(502, str(e))


@router.post("/cancel")
def cancel_my_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agenda cancelamento ao fim do período (não imediato)."""
    _stripe_required()

    sub = get_subscription(db, current_user.company_id)
    if not sub or not sub.stripe_subscription_id:
        raise HTTPException(404, "Assinatura não encontrada.")

    try:
        stripe.Subscription.modify(
            sub.stripe_subscription_id,
            cancel_at_period_end=True,
        )
        update_subscription_status(
            db, sub.stripe_subscription_id, sub.status,
            cancel_at_period_end=True
        )
        db.commit()
        return {
            "message": "Cancelamento agendado. Acesso mantido até o fim do período.",
            "valid_until": sub.current_period_end.isoformat() if sub.current_period_end else None,
        }
    except stripe.StripeError as e:
        raise HTTPException(502, str(e))


# ---------------------------------------------------------------------------
# Webhook — ponto crítico de segurança
# ---------------------------------------------------------------------------

@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    """
    Recebe e processa eventos Stripe via webhook.
    Sempre retorna 200 para evitar reenvios — erros internos são logados.
    """
    payload = await request.body()

    # Verifica assinatura HMAC
    if WEBHOOK_SECRET and not WEBHOOK_SECRET.startswith("whsec_your"):
        try:
            event = stripe.Webhook.construct_event(payload, stripe_signature, WEBHOOK_SECRET)
        except stripe.SignatureVerificationError:
            raise HTTPException(400, "Assinatura webhook inválida")
    else:
        logger.warning("Webhook sem verificação HMAC — configure STRIPE_WEBHOOK_SECRET em produção")
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            raise HTTPException(400, "Payload inválido")

    event_type = event.get("type", "")
    logger.info("Stripe webhook: %s", event_type)

    try:
        handlers = {
            "checkout.session.completed":     _on_checkout_completed,
            "customer.subscription.updated":  _on_subscription_updated,
            "customer.subscription.deleted":  _on_subscription_deleted,
            "invoice.payment_failed":         _on_payment_failed,
            "invoice.payment_succeeded":      _on_payment_succeeded,
            "customer.subscription.trial_will_end": _on_trial_ending,
        }
        handler = handlers.get(event_type)
        if handler:
            handler(event["data"]["object"], db)
            db.commit()
        else:
            logger.debug("Evento não tratado: %s", event_type)

    except Exception as e:
        db.rollback()
        logger.error("Erro ao processar webhook %s: %s", event_type, e, exc_info=True)

    return JSONResponse({"received": True})


# ---------------------------------------------------------------------------
# Handlers de webhook
# ---------------------------------------------------------------------------

def _on_checkout_completed(session: dict, db: Session) -> None:
    metadata    = session.get("metadata", {})
    company_id  = int(metadata.get("company_id", 0))
    plan        = metadata.get("plan", "starter")
    extra_seats = int(metadata.get("extra_seats", 0))

    if not company_id:
        logger.warning("checkout.completed sem company_id: %s", session.get("id"))
        return

    sub_id      = session.get("subscription", "")
    customer_id = session.get("customer", "")

    period_start = period_end = None
    price_id = ""
    if sub_id:
        try:
            stripe_sub   = stripe.Subscription.retrieve(sub_id)
            period_start = datetime.fromtimestamp(stripe_sub["current_period_start"], tz=timezone.utc)
            period_end   = datetime.fromtimestamp(stripe_sub["current_period_end"],   tz=timezone.utc)
            price_id     = stripe_sub["items"]["data"][0]["price"]["id"] if stripe_sub["items"]["data"] else ""
        except Exception as e:
            logger.error("Erro ao buscar subscription Stripe: %s", e)

    activate_subscription(
        db, company_id, plan, sub_id, customer_id, price_id,
        period_start or datetime.now(timezone.utc),
        period_end   or datetime.now(timezone.utc),
        extra_seats,
    )

    # Atualiza stripe_customer_id na empresa
    from database.crud import get_company_by_id
    company = get_company_by_id(db, company_id)
    if company and customer_id:
        company.stripe_customer_id = customer_id

    logger.info("Assinatura ativada: company_id=%d plan=%s", company_id, plan)


def _on_subscription_updated(stripe_sub: dict, db: Session) -> None:
    sub_id      = stripe_sub.get("id", "")
    new_status  = stripe_sub.get("status", "active")
    period_end  = (
        datetime.fromtimestamp(stripe_sub["current_period_end"], tz=timezone.utc)
        if stripe_sub.get("current_period_end") else None
    )
    cancel_flag = stripe_sub.get("cancel_at_period_end", False)

    sub = update_subscription_status(db, sub_id, new_status, period_end, cancel_flag)
    if sub:
        # Verifica se mudou de plano (upgrade/downgrade)
        new_plan = _plan_from_stripe_sub(stripe_sub)
        if new_plan and new_plan != sub.tier:
            defaults = TIER_DEFAULTS.get(new_plan, {})
            sub.tier               = new_plan
            sub.seats_included     = defaults.get("seats_included", sub.seats_included)
            sub.ncm_limit          = defaults.get("ncm_limit", sub.ncm_limit)
            sub.ai_queries_limit   = defaults.get("ai_queries_limit", sub.ai_queries_limit)
            logger.info("Plano alterado: sub_id=%s → %s", sub_id, new_plan)


def _on_subscription_deleted(stripe_sub: dict, db: Session) -> None:
    sub_id = stripe_sub.get("id", "")
    sub    = cancel_subscription(db, sub_id)
    if sub:
        logger.info("Assinatura cancelada: company_id=%d", sub.company_id)


def _on_payment_failed(invoice: dict, db: Session) -> None:
    sub_id = invoice.get("subscription", "")
    if sub_id:
        update_subscription_status(db, sub_id, "past_due")
        logger.warning("Pagamento falhou: sub_id=%s", sub_id)


def _on_payment_succeeded(invoice: dict, db: Session) -> None:
    sub_id = invoice.get("subscription", "")
    if sub_id:
        sub = get_subscription_by_stripe_id(db, sub_id)
        if sub and sub.status == "past_due":
            update_subscription_status(db, sub_id, "active")
            logger.info("Pagamento recuperado: sub_id=%s", sub_id)


def _on_trial_ending(stripe_sub: dict, db: Session) -> None:
    logger.info("Trial encerrando: sub_id=%s", stripe_sub.get("id"))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _plan_from_stripe_sub(stripe_sub: dict) -> Optional[str]:
    try:
        price_id = stripe_sub["items"]["data"][0]["price"]["id"]
        for plan, pid in PRICE_IDS.items():
            if pid == price_id:
                return plan
    except Exception:
        pass
    return stripe_sub.get("metadata", {}).get("plan")
