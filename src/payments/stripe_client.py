"""
stripe_client.py
================
PharmaIntel BR — Stripe payment integration.

Plans (BRL):
    Starter:    R$297/mês | R$799/trim | R$1.497/sem | R$2.697/ano
    Pro:        R$697/mês | R$1.897/trim | R$3.497/sem | R$6.697/ano
    Enterprise: R$1.497/mês | R$3.997/trim | R$7.497/sem | R$13.997/ano

Requires:
    STRIPE_SECRET_KEY     → sk_live_... or sk_test_...
    STRIPE_WEBHOOK_SECRET → whsec_...
    STRIPE_PUBLISHABLE_KEY → pk_live_... or pk_test_...
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import stripe as _stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    _stripe = None  # type: ignore


# ---------------------------------------------------------------------------
# Pricing catalogue
# ---------------------------------------------------------------------------

PLANS: dict[str, dict] = {
    "starter": {
        "name":        "Starter",
        "color":       "#4DB6AC",
        "description": "Para importadores iniciando o monitoramento",
        "features": [
            "Dashboard completo de importações",
            "3 NCMs monitorados",
            "Alertas ANVISA básicos",
            "Dados Comex Stat em tempo real",
            "Suporte por email",
        ],
        "prices": {
            "monthly":   {"brl": 49900,  "usd": 19900,  "label": "R$ 499",   "usd_label": "US$ 199",   "period_label": "por mês"},
            "quarterly": {"brl": 134900, "usd": 53700,  "label": "R$ 1.349", "usd_label": "US$ 537",   "period_label": "a cada 3 meses", "saving": "Economize 10%"},
            "biannual":  {"brl": 254900, "usd": 101400, "label": "R$ 2.549", "usd_label": "US$ 1.014", "period_label": "a cada 6 meses", "saving": "Economize 15%"},
            "annual":    {"brl": 479900, "usd": 191400, "label": "R$ 4.799", "usd_label": "US$ 1.914", "period_label": "por ano",         "saving": "Economize 20%"},
        },
    },
    "pro": {
        "name":        "Pro",
        "color":       "#00897B",
        "description": "Para importadores em crescimento",
        "features": [
            "Tudo do Starter",
            "NCMs ilimitados",
            "Alertas ANVISA completos + vencimentos",
            "Agente IA Groq/Llama 3.3 70B",
            "Dados UN Comtrade",
            "Relatórios exportáveis",
            "Suporte prioritário",
        ],
        "prices": {
            "monthly":   {"brl": 75000,  "usd": 39900,  "label": "R$ 750",   "usd_label": "US$ 399",   "period_label": "por mês"},
            "quarterly": {"brl": 202500, "usd": 107700, "label": "R$ 2.025", "usd_label": "US$ 1.077", "period_label": "a cada 3 meses", "saving": "Economize 10%"},
            "biannual":  {"brl": 382500, "usd": 203400, "label": "R$ 3.825", "usd_label": "US$ 2.034", "period_label": "a cada 6 meses", "saving": "Economize 15%"},
            "annual":    {"brl": 720000, "usd": 383000, "label": "R$ 7.200", "usd_label": "US$ 3.830", "period_label": "por ano",         "saving": "Economize 20%"},
        },
    },
    "enterprise": {
        "name":        "Enterprise",
        "color":       "#26C6DA",
        "description": "Para grandes operações e grupos empresariais",
        "features": [
            "Tudo do Pro",
            "Acesso à API REST",
            "White-label disponível",
            "Múltiplos usuários",
            "Relatórios personalizados",
            "Integração ERP/BI",
            "Suporte dedicado + SLA",
        ],
        "prices": {
            "monthly":   {"brl": 159900, "usd": 69900,  "label": "R$ 1.599", "usd_label": "US$ 699",   "period_label": "por mês"},
            "quarterly": {"brl": 431700, "usd": 188700, "label": "R$ 4.317", "usd_label": "US$ 1.887", "period_label": "a cada 3 meses", "saving": "Economize 10%"},
            "biannual":  {"brl": 815900, "usd": 356500, "label": "R$ 8.159", "usd_label": "US$ 3.565", "period_label": "a cada 6 meses", "saving": "Economize 15%"},
            "annual":    {"brl": 1535000,"usd": 671000, "label": "R$ 15.350","usd_label": "US$ 6.710", "period_label": "por ano",         "saving": "Economize 20%"},
        },
    },
}

PERIOD_MONTHS = {
    "monthly": 1,
    "quarterly": 3,
    "biannual": 6,
    "annual": 12,
}

PERIOD_LABEL_PT = {
    "monthly":   "Mensal",
    "quarterly": "Trimestral",
    "biannual":  "Semestral",
    "annual":    "Anual",
}


# ---------------------------------------------------------------------------
# Stripe client
# ---------------------------------------------------------------------------

def _get_stripe():
    """Return configured stripe module or raise."""
    if not STRIPE_AVAILABLE:
        raise RuntimeError("stripe package not installed")
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    _stripe.api_key = key
    return _stripe


@dataclass
class CheckoutResult:
    url: str
    session_id: str
    error: str = ""


def create_checkout_session(
    plan: str,
    period: str,
    email: str,
    success_url: str,
    cancel_url: str,
    customer_id: str = "",
) -> CheckoutResult:
    """
    Create a Stripe Checkout session for the given plan + period.

    Args:
        plan:        "starter" | "pro" | "enterprise"
        period:      "monthly" | "quarterly" | "biannual" | "annual"
        email:       Customer email
        success_url: URL after successful payment (include {CHECKOUT_SESSION_ID})
        cancel_url:  URL if customer cancels
        customer_id: Existing Stripe customer ID (optional)

    Returns:
        CheckoutResult with url and session_id
    """
    try:
        stripe = _get_stripe()
        plan_data   = PLANS[plan]
        price_data  = plan_data["prices"][period]
        months      = PERIOD_MONTHS[period]

        # Build price inline (no pre-created Price IDs needed)
        price_kwargs = {
            "currency": "usd",
            "unit_amount": price_data["usd"],  # USD cents — matches usd_label displayed to user
        }
        if period == "monthly":
            price_kwargs["recurring"] = {"interval": "month", "interval_count": 1}
        elif period == "quarterly":
            price_kwargs["recurring"] = {"interval": "month", "interval_count": 3}
        elif period == "biannual":
            price_kwargs["recurring"] = {"interval": "month", "interval_count": 6}
        elif period == "annual":
            price_kwargs["recurring"] = {"interval": "year", "interval_count": 1}

        session_kwargs: dict = {
            "mode": "subscription",
            "line_items": [{
                "price_data": {
                    **price_kwargs,
                    "product_data": {
                        "name": f"PharmaIntel BR — {plan_data['name']} ({PERIOD_LABEL_PT[period]})",
                        "description": plan_data["description"],
                    },
                },
                "quantity": 1,
            }],
            "success_url": success_url,
            "cancel_url":  cancel_url,
            "metadata": {
                "plan":   plan,
                "period": period,
                "email":  email,
            },
            "subscription_data": {
                "metadata": {"plan": plan, "period": period},
            },
            "allow_promotion_codes": True,
            "billing_address_collection": "auto",
        }

        if customer_id:
            session_kwargs["customer"] = customer_id
        else:
            session_kwargs["customer_email"] = email

        session = stripe.checkout.Session.create(**session_kwargs)
        return CheckoutResult(url=session.url, session_id=session.id)

    except Exception as exc:
        logger.error("Stripe checkout error: %s", exc)
        return CheckoutResult(url="", session_id="", error=str(exc))


@dataclass
class SessionInfo:
    customer_id:     str = ""
    subscription_id: str = ""
    email:           str = ""
    plan:            str = ""
    period:          str = ""
    status:          str = ""
    error:           str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.status in ("complete", "active")


def verify_checkout_session(session_id: str) -> SessionInfo:
    """Verify a completed Stripe Checkout session and extract subscription info."""
    try:
        stripe  = _get_stripe()
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription", "customer"])

        meta   = session.get("metadata") or {}
        plan   = meta.get("plan", "")
        period = meta.get("period", "")
        email  = session.get("customer_details", {}).get("email", "") or meta.get("email", "")

        sub = session.get("subscription")
        sub_id = sub.get("id", "") if isinstance(sub, dict) else (sub or "")

        cust = session.get("customer")
        cust_id = cust.get("id", "") if isinstance(cust, dict) else (cust or "")

        return SessionInfo(
            customer_id=cust_id,
            subscription_id=sub_id,
            email=email,
            plan=plan,
            period=period,
            status=session.get("payment_status", ""),
        )
    except Exception as exc:
        logger.error("Stripe session verify error: %s", exc)
        return SessionInfo(error=str(exc))


def create_customer_portal_session(customer_id: str, return_url: str) -> str:
    """Create a Stripe Customer Portal session URL for subscription management."""
    try:
        stripe  = _get_stripe()
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url
    except Exception as exc:
        logger.error("Stripe portal error: %s", exc)
        return ""


def construct_webhook_event(payload: bytes, sig_header: str):
    """Construct and verify a Stripe webhook event."""
    stripe  = _get_stripe()
    secret  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def is_configured() -> bool:
    """Return True if Stripe secret key is set."""
    return bool(os.getenv("STRIPE_SECRET_KEY", ""))
