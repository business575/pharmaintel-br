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
        "name":         "Starter",
        "color":        "#4DB6AC",
        "description":  "Comece agora — dados e alertas para seu negócio",
        "description_en": "Start now — data and alerts for your business",
        "ai_model":     "AI",
        "features": [
            "Dashboard completo de importações",
            "NCMs ilimitados monitorados",
            "Alertas ANVISA básicos",
            "Dados Comex Stat em tempo real",
            "Agente IA integrado",
            "Suporte por email",
        ],
        "features_en": [
            "Full import dashboard",
            "Unlimited NCM/HS codes monitored",
            "Basic ANVISA alerts",
            "Real-time Comex Stat data",
            "Integrated AI Agent",
            "Email support",
        ],
        "prices": {
            "monthly":   {"brl": 49700,  "usd": 29900,  "label": "R$ 497",   "usd_label": "US$ 299",   "period_label": "por mês"},
            "quarterly": {"brl": 134190, "usd": 80730,  "label": "R$ 1.342", "usd_label": "US$ 807",   "period_label": "a cada 3 meses", "saving": "Economize 10%"},
            "biannual":  {"brl": 253470, "usd": 152490, "label": "R$ 2.535", "usd_label": "US$ 1.525", "period_label": "a cada 6 meses", "saving": "Economize 15%"},
            "annual":    {"brl": 477120, "usd": 287040, "label": "R$ 4.771", "usd_label": "US$ 2.870", "period_label": "por ano",         "saving": "Economize 20%"},
        },
    },
    "pro": {
        "name":         "Pro",
        "color":        "#00897B",
        "description":  "Análise precisa — IA superior para decisões estratégicas",
        "description_en": "Precise analysis — superior AI for strategic decisions",
        "ai_model":     "Advanced AI",
        "features": [
            "Tudo do Starter",
            "Agente IA de alta precisão",
            "Alertas ANVISA completos + vencimentos",
            "Patentes e oportunidades de biossimilares",
            "Dados UN Comtrade",
            "Relatórios exportáveis PDF/Excel",
            "Suporte prioritário",
        ],
        "features_en": [
            "Everything in Starter",
            "High-accuracy AI Agent",
            "Full ANVISA alerts + expiry tracking",
            "Patent expiration and biosimilar opportunities",
            "UN Comtrade global data",
            "Exportable PDF/Excel reports",
            "Priority support",
        ],
        "prices": {
            "monthly":   {"brl": 99700,  "usd": 49900,  "label": "R$ 997",   "usd_label": "US$ 499",   "period_label": "por mês"},
            "quarterly": {"brl": 269190, "usd": 134730, "label": "R$ 2.692", "usd_label": "US$ 1.347", "period_label": "a cada 3 meses", "saving": "Economize 10%"},
            "biannual":  {"brl": 508470, "usd": 254490, "label": "R$ 5.085", "usd_label": "US$ 2.545", "period_label": "a cada 6 meses", "saving": "Economize 15%"},
            "annual":    {"brl": 957120, "usd": 479040, "label": "R$ 9.571", "usd_label": "US$ 4.790", "period_label": "por ano",         "saving": "Economize 20%"},
        },
    },
    "enterprise": {
        "name":         "Enterprise",
        "color":        "#26C6DA",
        "description":  "Sua equipe toda — API, white-label e suporte dedicado",
        "description_en": "Your whole team — API, white-label and dedicated support",
        "ai_model":     "Enterprise AI + API",
        "features": [
            "Tudo do Pro",
            "Acesso à API REST completa",
            "White-label disponível",
            "Múltiplos usuários e perfis",
            "Relatórios personalizados",
            "Integração ERP/BI",
            "Suporte dedicado + SLA garantido",
        ],
        "features_en": [
            "Everything in Pro",
            "Full REST API access",
            "White-label available",
            "Multiple users and profiles",
            "Custom reports",
            "ERP/BI integration",
            "Dedicated support + guaranteed SLA",
        ],
        "prices": {
            "monthly":   {"brl": 249700, "usd": 149900, "label": "R$ 2.497", "usd_label": "US$ 1.499", "period_label": "por mês"},
            "quarterly": {"brl": 674190, "usd": 404730, "label": "R$ 6.742", "usd_label": "US$ 4.047", "period_label": "a cada 3 meses", "saving": "Economize 10%"},
            "biannual":  {"brl": 1273470,"usd": 764490, "label": "R$ 12.735","usd_label": "US$ 7.645", "period_label": "a cada 6 meses", "saving": "Economize 15%"},
            "annual":    {"brl": 2397120,"usd": 1439040,"label": "R$ 23.971","usd_label": "US$ 14.390","period_label": "por ano",         "saving": "Economize 20%"},
        },
    },
}

PERIOD_MONTHS = {
    "monthly": 1,
    "quarterly": 3,
    "biannual": 6,
    "annual": 12,
}

PERIOD_LABEL_EN = {
    "monthly":   "Monthly",
    "quarterly": "Quarterly",
    "biannual":  "Biannual",
    "annual":    "Annual",
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
