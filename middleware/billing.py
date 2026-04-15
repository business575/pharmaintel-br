"""
middleware/billing.py
=====================
PharmaIntel BR — Controle de acesso por tier e rastreamento de uso.

Uso no Streamlit
----------------
    from middleware.billing import get_billing_context, check_feature, track_usage

    ctx = get_billing_context()   # lê session_state
    if check_feature(ctx, "anvisa_alerts"):
        render_alertas(alertas)
    else:
        render_upgrade_banner("Alertas ANVISA", "Pro")

    # Antes de chamar o agente IA:
    ok, msg = consume_ai_query(ctx)
    if not ok:
        st.warning(msg)

Uso no FastAPI (dependency injection)
--------------------------------------
    @router.get("/endpoint")
    def endpoint(billing = Depends(require_tier("pro"))):
        ...
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from database.crud import (
    get_subscription,
    get_usage_count,
    increment_ai_usage,
    log_usage,
)
from database.models import Subscription, get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature matrix por tier
# ---------------------------------------------------------------------------

TIER_FEATURES: dict[str, dict] = {
    "none": {
        "max_ncms":       0,
        "anvisa_alerts":  False,
        "comprasnet":     False,
        "ai_agent":       False,
        "api_access":     False,
        "white_label":    False,
        "etl_runner":     False,
        "export":         False,
        "multi_year":     False,
        "max_users":      0,
    },
    "starter": {
        "max_ncms":       5,
        "anvisa_alerts":  False,
        "comprasnet":     False,
        "ai_agent":       False,
        "api_access":     False,
        "white_label":    False,
        "etl_runner":     True,
        "export":         False,
        "multi_year":     False,
        "max_users":      1,
    },
    "pro": {
        "max_ncms":       -1,     # ilimitado
        "anvisa_alerts":  True,
        "comprasnet":     True,
        "ai_agent":       True,
        "api_access":     False,
        "white_label":    False,
        "etl_runner":     True,
        "export":         True,
        "multi_year":     True,
        "max_users":      3,
    },
    "enterprise": {
        "max_ncms":       -1,
        "anvisa_alerts":  True,
        "comprasnet":     True,
        "ai_agent":       True,
        "api_access":     True,
        "white_label":    True,
        "etl_runner":     True,
        "export":         True,
        "multi_year":     True,
        "max_users":      10,
    },
}

TIER_DISPLAY = {
    "none":       ("Sem plano",   "#3A4455"),
    "starter":    ("Starter",     "#42A5F5"),
    "pro":        ("Pro",         "#00D4A1"),
    "enterprise": ("Enterprise",  "#FFB74D"),
}

UPGRADE_REQUIRED = {
    "anvisa_alerts":  "Pro",
    "comprasnet":     "Pro",
    "ai_agent":       "Pro",
    "api_access":     "Enterprise",
    "white_label":    "Enterprise",
    "export":         "Pro",
    "multi_year":     "Pro",
}


# ---------------------------------------------------------------------------
# BillingContext — contexto de billing para o Streamlit
# ---------------------------------------------------------------------------

@dataclass
class BillingContext:
    """
    Snapshot do estado de billing do usuário autenticado.
    Criado uma vez por request/rerun e passado para as funções de render.
    """
    authenticated:  bool   = False
    user_id:        int    = 0
    company_id:     int    = 0
    email:          str    = ""
    full_name:      str    = ""
    role:           str    = "member"
    tier:           str    = "none"
    status:         str    = "none"
    seats_used:     int    = 0
    seats_total:    int    = 0
    ai_used:        int    = 0
    ai_limit:       int    = 0
    ncm_limit:      int    = 0
    features:       dict   = field(default_factory=dict)
    period_end:     Optional[datetime] = None
    cancel_at_end:  bool   = False

    @property
    def is_active(self) -> bool:
        return self.authenticated and self.status in ("active", "trialing")

    @property
    def ai_unlimited(self) -> bool:
        return self.ai_limit == -1

    @property
    def ai_remaining(self) -> int:
        if self.ai_unlimited:
            return 9999
        return max(0, self.ai_limit - self.ai_used)

    def can(self, feature: str) -> bool:
        return bool(self.features.get(feature, False))

    def tier_display(self) -> tuple[str, str]:
        return TIER_DISPLAY.get(self.tier, ("Sem plano", "#3A4455"))

    def required_plan_for(self, feature: str) -> str:
        return UPGRADE_REQUIRED.get(feature, "Pro")


def get_billing_context() -> BillingContext:
    """
    Lê session_state do Streamlit e constrói BillingContext.
    Chamado no início de cada rerun.
    """
    try:
        import streamlit as st
        ss = st.session_state
    except Exception:
        return BillingContext()

    if not ss.get("authenticated", False):
        return BillingContext()

    tier   = ss.get("user_tier", "none")
    status = ss.get("sub_status", "none")
    feats  = TIER_FEATURES.get(tier, TIER_FEATURES["none"])

    # Reconstrói ai_used do session_state (evita query por rerun)
    return BillingContext(
        authenticated = True,
        user_id       = ss.get("user_id", 0),
        company_id    = ss.get("company_id", 0),
        email         = ss.get("user_email", ""),
        full_name     = ss.get("user_full_name", ""),
        role          = ss.get("user_role", "member"),
        tier          = tier,
        status        = status,
        seats_used    = ss.get("seats_used", 1),
        seats_total   = ss.get("seats_total", 1),
        ai_used       = ss.get("ai_queries_used", 0),
        ai_limit      = ss.get("ai_queries_limit", 0),
        ncm_limit     = ss.get("ncm_limit", 5),
        features      = feats,
        period_end    = ss.get("period_end"),
        cancel_at_end = ss.get("cancel_at_period_end", False),
    )


# ---------------------------------------------------------------------------
# Funções de verificação de features
# ---------------------------------------------------------------------------

def check_feature(ctx: BillingContext, feature: str) -> bool:
    """Retorna True se o tier atual tem acesso à feature."""
    return ctx.can(feature)


def track_usage(
    company_id: int,
    feature: str,
    user_id: int = None,
    metadata: dict = None,
) -> None:
    """Registra uso de uma feature no banco."""
    from database.models import db_session
    try:
        with db_session() as db:
            log_usage(db, company_id, feature, user_id, metadata)
    except Exception as e:
        logger.warning("Falha ao registrar uso: %s", e)


def consume_ai_query(ctx: BillingContext) -> tuple[bool, str]:
    """
    Tenta consumir 1 AI query. Retorna (ok, mensagem).
    Atualiza session_state e DB.
    """
    if not ctx.can("ai_agent"):
        return False, "Agente IA disponível a partir do plano Pro."

    if not ctx.ai_unlimited and ctx.ai_remaining <= 0:
        return False, (
            f"Limite de {ctx.ai_limit} queries de IA por mês atingido. "
            "Faça upgrade para Enterprise para uso ilimitado."
        )

    # Incrementa no DB
    try:
        from database.models import db_session
        with db_session() as db:
            sub = get_subscription(db, ctx.company_id)
            if sub:
                ok = increment_ai_usage(db, sub)
                if not ok:
                    return False, "Limite de AI queries atingido."

                # Atualiza session_state
                try:
                    import streamlit as st
                    st.session_state["ai_queries_used"] = sub.ai_queries_used
                except Exception:
                    pass

                log_usage(db, ctx.company_id, "ai_query", ctx.user_id)
                return True, ""
    except Exception as e:
        logger.error("Erro ao consumir AI query: %s", e)
        return True, ""  # Fail open para não bloquear o usuário

    return True, ""


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------

def require_tier(*tiers: str):
    """
    Dependency FastAPI: exige que a empresa do usuário tenha um dos tiers.

    Uso:
        @router.get("/pro-only")
        def endpoint(b = Depends(require_tier("pro", "enterprise"))):
            ...
    """
    from api.auth import get_current_user

    def _check(
        user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        sub = get_subscription(db, user.company_id)
        if not sub or not sub.is_active or sub.tier not in tiers:
            required = " ou ".join(t.title() for t in tiers)
            raise HTTPException(
                status_code=403,
                detail=f"Acesso restrito ao plano {required}. Faça upgrade.",
            )
        return sub

    return _check


def require_ai_quota():
    """Dependency FastAPI: verifica e incrementa quota de AI."""
    from api.auth import get_current_user

    def _check(
        user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        sub = get_subscription(db, user.company_id)
        if not sub or sub.tier not in ("pro", "enterprise"):
            raise HTTPException(403, "Agente IA disponível a partir do plano Pro.")

        ok = increment_ai_usage(db, sub)
        if not ok:
            raise HTTPException(
                429,
                detail=f"Limite de {sub.ai_queries_limit} queries de IA por mês atingido.",
            )
        log_usage(db, user.company_id, "ai_query", user.id)
        return sub

    return _check


def require_feature(feature: str):
    """Dependency FastAPI: verifica acesso a uma feature específica."""
    from api.auth import get_current_user

    def _check(
        user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        sub = get_subscription(db, user.company_id)
        tier = sub.tier if (sub and sub.is_active) else "none"
        feats = TIER_FEATURES.get(tier, TIER_FEATURES["none"])
        if not feats.get(feature, False):
            required = UPGRADE_REQUIRED.get(feature, "Pro")
            raise HTTPException(
                403,
                detail=f"Feature '{feature}' disponível a partir do plano {required}.",
            )
        return sub

    return _check
