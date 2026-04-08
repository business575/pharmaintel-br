"""
quota.py
========
PharmaIntel BR — Controle de cota de mensagens IA por cliente/mês.

Cotas por plano:
    Starter:    200 msgs/mês
    Pro:        600 msgs/mês
    Enterprise: Ilimitado

Armazenamento: data/ai_quota.json
    {
      "2026-04": {
        "user@email.com": {"plan": "starter", "used": 45, "limit": 200}
      }
    }

Reset automático no início de cada mês.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

QUOTA_PATH = Path(__file__).resolve().parents[2] / "data" / "ai_quota.json"

# Mensagens incluídas por plano por mês
PLAN_QUOTA: dict[str, int] = {
    "starter":    200,
    "pro":        600,
    "enterprise": 999_999,  # ilimitado na prática
    "admin":      999_999,
    "":           50,        # sem plano definido (trial/teste)
}


def _current_month() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m")


def _load() -> dict:
    if QUOTA_PATH.exists():
        try:
            return json.loads(QUOTA_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUOTA_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_user_quota(email: str, plan: str) -> dict:
    """
    Returns quota info for a user this month.
    {used, limit, remaining, pct_used, allowed}
    """
    month = _current_month()
    data  = _load()
    month_data = data.get(month, {})
    user_data  = month_data.get(email, {})

    limit = PLAN_QUOTA.get(plan or "", PLAN_QUOTA[""])
    used  = user_data.get("used", 0)
    remaining = max(limit - used, 0)
    pct   = round(used / limit * 100, 1) if limit < 999_999 else 0

    return {
        "email":     email,
        "plan":      plan,
        "month":     month,
        "used":      used,
        "limit":     limit,
        "remaining": remaining,
        "pct_used":  pct,
        "allowed":   used < limit,
        "unlimited": limit >= 999_999,
    }


def consume_message(email: str, plan: str) -> dict:
    """
    Consume 1 message from the user's quota.
    Returns updated quota dict.
    Call AFTER a successful AI response.
    """
    month = _current_month()
    data  = _load()

    if month not in data:
        data[month] = {}

    if email not in data[month]:
        data[month][email] = {"plan": plan, "used": 0, "limit": PLAN_QUOTA.get(plan or "", 50)}

    data[month][email]["used"] += 1
    data[month][email]["plan"]  = plan  # keep plan updated
    data[month][email]["limit"] = PLAN_QUOTA.get(plan or "", 50)

    _save(data)
    return get_user_quota(email, plan)


def quota_status_message(quota: dict) -> str:
    """Return a user-friendly message about quota status."""
    if quota["unlimited"]:
        return ""
    used      = quota["used"]
    limit     = quota["limit"]
    remaining = quota["remaining"]
    plan      = quota["plan"].capitalize() if quota["plan"] else "Sem plano"

    if not quota["allowed"]:
        return (
            f"🚫 **Cota de mensagens esgotada este mês.**\n\n"
            f"Plano {plan}: {limit} mensagens/mês — você usou todas as {used}.\n\n"
            f"A cota renova automaticamente em **1º do próximo mês**.\n"
            f"Para mais mensagens, faça upgrade para um plano superior."
        )
    if remaining <= 10:
        return f"⚠️ *Atenção: apenas {remaining} mensagens restantes este mês ({plan}).*"
    if quota["pct_used"] >= 80:
        return f"*{used}/{limit} mensagens usadas este mês ({plan}).*"
    return ""


def all_users_quota_summary() -> list[dict]:
    """Returns quota summary for all users this month — for admin dashboard."""
    month = _current_month()
    data  = _load()
    month_data = data.get(month, {})
    rows = []
    for email, info in month_data.items():
        limit = info.get("limit", 0)
        used  = info.get("used", 0)
        rows.append({
            "email":   email,
            "plan":    info.get("plan", ""),
            "used":    used,
            "limit":   limit,
            "pct":     round(used / limit * 100, 1) if limit and limit < 999_999 else 0,
        })
    return sorted(rows, key=lambda r: r["used"], reverse=True)
