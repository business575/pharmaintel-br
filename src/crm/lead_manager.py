"""
lead_manager.py - CRM lead management for PharmaIntel BR

Manages leads captured from the demo agent flow, tracks pipeline health,
and calculates revenue progress toward the R$50k goal.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, date
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LEADS_FILE = DATA_DIR / "demo_leads.json"

PLAN_PRICES = {
    "starter": 497,
    "pro": 997,
    "enterprise": 2497,
}


class LeadStatus(str, Enum):
    NEW = "new"
    DEMO_TESTED = "demo_tested"
    FOLLOW_UP_SENT = "follow_up_sent"
    CONTACTED = "contacted"
    SUBSCRIBED = "subscribed"
    LOST = "lost"


class LeadTemperature(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass
class Lead:
    email: str
    lang: str = "PT"
    status: str = LeadStatus.NEW
    temperature: str = LeadTemperature.COLD
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    questions_asked: int = 0
    last_contact: Optional[str] = None
    notes: str = ""
    country_hint: str = ""
    follow_up_count: int = 0
    emails_sent: list = field(default_factory=list)
    follow_up_sent: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Lead":
        allowed = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in d.items() if k in allowed}
        # Ensure emails_sent is always a list
        if "emails_sent" not in filtered or filtered["emails_sent"] is None:
            filtered["emails_sent"] = []
        return cls(**filtered)

    def _compute_temperature(self) -> str:
        if self.questions_asked >= 2:
            return LeadTemperature.HOT
        elif self.questions_asked == 1:
            return LeadTemperature.WARM
        return LeadTemperature.COLD


class LeadManager:
    """Manages demo leads from JSON file + subscriber data from SQLite."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._leads: dict[str, Lead] = {}
        self._load()

    def _load(self) -> None:
        """Load leads from demo_leads.json and merge with DB subscribers."""
        # Load JSON leads
        if LEADS_FILE.exists():
            try:
                raw = json.loads(LEADS_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    for item in raw:
                        try:
                            lead = Lead.from_dict(item)
                            self._leads[lead.email.lower()] = lead
                        except Exception as exc:
                            logger.warning("Skipping malformed lead: %s", exc)
            except Exception as exc:
                logger.warning("Failed to load demo_leads.json: %s", exc)

        # Merge active subscribers from SQLite
        try:
            from src.db.database import init_db, SessionLocal
            from src.db.models import User
            init_db()
            with SessionLocal() as s:
                users = s.query(User).filter(User.subscription_status == "active").all()
                for u in users:
                    email = u.email.lower()
                    if email in self._leads:
                        self._leads[email].status = LeadStatus.SUBSCRIBED
                    else:
                        lead = Lead(
                            email=email,
                            status=LeadStatus.SUBSCRIBED,
                            temperature=LeadTemperature.HOT,
                        )
                        self._leads[email] = lead
        except Exception as exc:
            logger.debug("DB merge skipped: %s", exc)

    def get_all_leads(self) -> list[Lead]:
        """Return all leads sorted by timestamp descending."""
        leads = list(self._leads.values())
        leads.sort(key=lambda l: l.timestamp or "", reverse=True)
        return leads

    def get_hot_leads(self) -> list[Lead]:
        """Return leads most likely to convert (hot or warm, not yet subscribed)."""
        results = []
        for lead in self._leads.values():
            if lead.status == LeadStatus.SUBSCRIBED:
                continue
            temp = lead._compute_temperature()
            if temp in (LeadTemperature.HOT, LeadTemperature.WARM):
                results.append(lead)
        results.sort(key=lambda l: l.questions_asked, reverse=True)
        return results

    def update_lead(self, email: str, **kwargs) -> bool:
        """Update fields on an existing lead. Returns True if found."""
        key = email.lower()
        if key not in self._leads:
            return False
        lead = self._leads[key]
        for attr, val in kwargs.items():
            if hasattr(lead, attr):
                setattr(lead, attr, val)
        # Recompute temperature based on questions_asked
        lead.temperature = lead._compute_temperature()
        return True

    def add_or_update(self, email: str, lang: str = "PT", questions_asked: int = 0,
                      country_hint: str = "", notes: str = "") -> Lead:
        """Add a new lead or update existing one from demo interaction."""
        key = email.lower()
        if key in self._leads:
            lead = self._leads[key]
            # Only increase question count
            if questions_asked > lead.questions_asked:
                lead.questions_asked = questions_asked
            if country_hint:
                lead.country_hint = country_hint
            if notes:
                lead.notes = notes
            lead.temperature = lead._compute_temperature()
            if lead.status == LeadStatus.NEW and questions_asked > 0:
                lead.status = LeadStatus.DEMO_TESTED
        else:
            status = LeadStatus.DEMO_TESTED if questions_asked > 0 else LeadStatus.NEW
            lead = Lead(
                email=key,
                lang=lang,
                status=status,
                questions_asked=questions_asked,
                country_hint=country_hint,
                notes=notes,
            )
            lead.temperature = lead._compute_temperature()
            self._leads[key] = lead
        self.save()
        return lead

    def get_pipeline_stats(self) -> dict:
        """Return pipeline counts by status and conversion metrics."""
        leads = self.get_all_leads()
        total = len(leads)
        by_status: dict[str, int] = {}
        for s in LeadStatus:
            by_status[s.value] = sum(1 for l in leads if l.status == s.value)

        subscribed = by_status.get(LeadStatus.SUBSCRIBED, 0)
        contacted = by_status.get(LeadStatus.CONTACTED, 0)
        demo_tested = by_status.get(LeadStatus.DEMO_TESTED, 0)
        hot_count = len(self.get_hot_leads())

        conversion_rate = (subscribed / total * 100) if total > 0 else 0.0
        demo_to_sub = (subscribed / (demo_tested + subscribed + contacted) * 100) \
            if (demo_tested + subscribed + contacted) > 0 else 0.0

        revenue_actual = self.get_revenue_actual()
        revenue_potential = hot_count * PLAN_PRICES["pro"]  # estimate hot leads at Pro

        return {
            "total": total,
            "by_status": by_status,
            "hot": hot_count,
            "conversion_rate": round(conversion_rate, 1),
            "demo_to_sub_rate": round(demo_to_sub, 1),
            "revenue_actual": revenue_actual,
            "revenue_potential": revenue_potential,
        }

    def get_revenue_actual(self) -> float:
        """Query SQLite for active subscribers and compute revenue."""
        total = 0.0
        try:
            from src.db.database import init_db, SessionLocal
            from src.db.models import User
            init_db()
            with SessionLocal() as s:
                users = s.query(User).filter(User.subscription_status == "active").all()
                for u in users:
                    price = PLAN_PRICES.get(u.plan or "starter", PLAN_PRICES["starter"])
                    total += price
        except Exception as exc:
            logger.debug("Revenue query failed: %s", exc)
        return total

    def get_days_to_goal(
        self,
        goal: float = 50000.0,
        start_date: str = "2026-04-09",
        end_date: str = "2026-04-30",
    ) -> dict:
        """Return progress info toward revenue goal."""
        today = date.today()
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError:
            start = today
            end = today

        total_days = max((end - start).days, 1)
        days_elapsed = max((today - start).days, 0)
        days_remaining = max((end - today).days, 0)

        revenue = self.get_revenue_actual()
        remaining = max(goal - revenue, 0.0)
        pct = min((revenue / goal) * 100, 100.0)

        # Sales needed per day to hit goal
        daily_target = remaining / days_remaining if days_remaining > 0 else 0.0

        # Estimate subscriptions needed at avg Pro price
        avg_price = PLAN_PRICES["pro"]
        subs_needed = int(remaining / avg_price) + (1 if remaining % avg_price else 0)

        return {
            "goal": goal,
            "revenue": revenue,
            "remaining": remaining,
            "pct": round(pct, 1),
            "days_remaining": days_remaining,
            "days_elapsed": days_elapsed,
            "total_days": total_days,
            "daily_target": round(daily_target, 0),
            "subs_needed": subs_needed,
            "on_track": revenue >= (goal * days_elapsed / total_days) if total_days > 0 else False,
        }

    def mark_contacted(self, email: str, notes: str = "") -> bool:
        """Update lead status to contacted."""
        key = email.lower()
        if key not in self._leads:
            return False
        lead = self._leads[key]
        lead.status = LeadStatus.CONTACTED
        lead.last_contact = datetime.now(timezone.utc).isoformat()
        lead.follow_up_count += 1
        if notes:
            lead.notes = f"{lead.notes}\n{notes}".strip()
        self.save()
        return True

    def save(self) -> None:
        """Persist leads to demo_leads.json (excluding DB-only subscribers)."""
        try:
            data = [lead.to_dict() for lead in self._leads.values()]
            LEADS_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to save leads: %s", exc)
