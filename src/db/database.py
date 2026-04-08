"""
database.py
===========
PharmaIntel BR — Database connection (SQLite via SQLAlchemy).

On Render free tier, the filesystem is ephemeral, so use a persistent
disk or an external DB for production. For MVP, SQLite is fine.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "pharmaintel.db"
_DB_URL  = os.getenv("DATABASE_URL", f"sqlite:///{_DB_PATH}")

# SQLite: check_same_thread=False needed for Streamlit's multi-thread model
_connect_args = {"check_same_thread": False} if _DB_URL.startswith("sqlite") else {}

engine = create_engine(_DB_URL, connect_args=_connect_args, echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create all tables if they don't exist."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Return a new database session. Caller is responsible for closing."""
    return SessionLocal()


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------
def get_user_by_email(email: str) -> "User | None":
    from src.db.models import User
    with SessionLocal() as s:
        return s.query(User).filter(User.email == email.lower().strip()).first()


def create_user(
    email: str,
    password: str,
    full_name: str = "",
    plan: str = "",
    period: str = "",
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    subscription_status: str = "active",
    subscription_end=None,
) -> "User":
    from src.db.models import User
    with SessionLocal() as s:
        user = User(
            email=email.lower().strip(),
            password_hash=User.hash_password(password),
            full_name=full_name,
            plan=plan,
            period=period,
            is_active=True,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            subscription_status=subscription_status,
            subscription_end=subscription_end,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


def create_trial_user(email: str, password: str, full_name: str = "") -> "User":
    """Create a free-trial account (7 days, Starter plan, no payment required)."""
    from datetime import datetime, timezone, timedelta
    from src.db.models import User, TRIAL_DAYS
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        user = User(
            email=email.lower().strip(),
            password_hash=User.hash_password(password),
            full_name=full_name,
            plan="starter",
            period="trial",
            is_active=True,
            is_trial=True,
            trial_start=now,
            subscription_status="trialing",
            subscription_end=now + timedelta(days=TRIAL_DAYS),
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


def update_subscription(
    stripe_customer_id: str,
    subscription_id: str,
    status: str,
    plan: str = "",
    period: str = "",
    subscription_end=None,
) -> bool:
    from src.db.models import User
    with SessionLocal() as s:
        user = s.query(User).filter(User.stripe_customer_id == stripe_customer_id).first()
        if not user:
            return False
        user.stripe_subscription_id = subscription_id
        user.subscription_status    = status
        user.is_active              = status in ("active", "trialing")
        if plan:
            user.plan = plan
        if period:
            user.period = period
        if subscription_end:
            user.subscription_end = subscription_end
        s.commit()
        return True


def save_demo_lead(
    email: str,
    lang: str = "PT",
    status: str = "new",
    temperature: str = "cold",
    questions_asked: int = 0,
    country_hint: str = "",
) -> None:
    """Create or update a demo lead in the database."""
    import json
    from src.db.models import DemoLead
    from datetime import datetime, timezone
    with SessionLocal() as s:
        lead = s.query(DemoLead).filter(DemoLead.email == email.lower().strip()).first()
        if lead:
            if questions_asked > lead.questions_asked:
                lead.questions_asked = questions_asked
            if temperature in ("hot", "warm") and lead.temperature == "cold":
                lead.temperature = temperature
            if status != "new":
                lead.status = status
            lead.updated_at = datetime.now(timezone.utc)
        else:
            lead = DemoLead(
                email=email.lower().strip(),
                lang=lang,
                status=status,
                temperature=temperature,
                questions_asked=questions_asked,
                country_hint=country_hint,
                emails_sent="[]",
            )
            s.add(lead)
        s.commit()


def get_demo_leads() -> list:
    """Return all demo leads as dicts."""
    import json
    from src.db.models import DemoLead
    with SessionLocal() as s:
        leads = s.query(DemoLead).order_by(DemoLead.created_at.desc()).all()
        result = []
        for l in leads:
            result.append({
                "email": l.email,
                "lang": l.lang,
                "status": l.status,
                "temperature": l.temperature,
                "questions_asked": l.questions_asked,
                "country_hint": l.country_hint,
                "notes": l.notes,
                "follow_up_count": l.follow_up_count,
                "emails_sent": json.loads(l.emails_sent or "[]"),
                "last_contact": l.last_contact.isoformat() if l.last_contact else None,
                "timestamp": l.created_at.isoformat(),
            })
        return result


def update_demo_lead(email: str, **kwargs) -> None:
    """Update fields on a demo lead."""
    import json
    from src.db.models import DemoLead
    from datetime import datetime, timezone
    with SessionLocal() as s:
        lead = s.query(DemoLead).filter(DemoLead.email == email.lower().strip()).first()
        if not lead:
            return
        for k, v in kwargs.items():
            if k == "emails_sent" and isinstance(v, list):
                v = json.dumps(v)
            if hasattr(lead, k):
                setattr(lead, k, v)
        lead.updated_at = datetime.now(timezone.utc)
        s.commit()


def get_prospects(status: str = None, limit: int = 100) -> list:
    """Return prospects as list of dicts."""
    from src.db.models import Prospect
    with SessionLocal() as s:
        q = s.query(Prospect)
        if status:
            q = q.filter(Prospect.status == status)
        q = q.order_by(Prospect.created_at.desc()).limit(limit)
        result = []
        for p in q.all():
            result.append({
                "id": p.id,
                "company_name": p.company_name,
                "email": p.email,
                "phone": p.phone,
                "contact_role": p.contact_role,
                "segment": p.segment,
                "description": p.description,
                "is_partner": p.is_partner,
                "status": p.status,
                "emails_sent": p.emails_sent,
                "last_contact": p.last_contact.isoformat() if p.last_contact else None,
                "last_email_body": p.last_email_body,
                "notes": p.notes,
                "priority": p.priority,
            })
        return result


def add_prospect(company_name: str, email: str, phone: str = "", contact_role: str = "",
                 segment: str = "", description: str = "", is_partner: bool = False,
                 priority: str = "high") -> None:
    """Add a new prospect if email not already in DB."""
    from src.db.models import Prospect
    with SessionLocal() as s:
        existing = s.query(Prospect).filter(Prospect.email == email.lower().strip()).first()
        if existing:
            return
        s.add(Prospect(
            company_name=company_name,
            email=email.lower().strip(),
            phone=phone,
            contact_role=contact_role,
            segment=segment,
            description=description,
            is_partner=is_partner,
            priority=priority,
        ))
        s.commit()


def update_prospect(prospect_id: int, **kwargs) -> None:
    """Update fields on a prospect."""
    from src.db.models import Prospect
    from datetime import datetime, timezone
    with SessionLocal() as s:
        p = s.query(Prospect).filter(Prospect.id == prospect_id).first()
        if not p:
            return
        for k, v in kwargs.items():
            if hasattr(p, k):
                setattr(p, k, v)
        p.updated_at = datetime.now(timezone.utc)
        s.commit()


def get_prospects_due_today(daily_limit: int = 20) -> list:
    """Return pending prospects up to daily_limit, not contacted today."""
    from src.db.models import Prospect
    from datetime import datetime, timezone, timedelta
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal() as s:
        prospects = (
            s.query(Prospect)
            .filter(Prospect.status == "pending")
            .filter(
                (Prospect.last_contact == None) |
                (Prospect.last_contact < today_start)
            )
            .order_by(Prospect.priority.desc(), Prospect.created_at.asc())
            .limit(daily_limit)
            .all()
        )
        result = []
        for p in prospects:
            result.append({
                "id": p.id,
                "company_name": p.company_name,
                "email": p.email,
                "phone": p.phone,
                "contact_role": p.contact_role,
                "segment": p.segment,
                "description": p.description,
                "is_partner": p.is_partner,
                "priority": p.priority,
            })
        return result


def webhook_seen(event_id: str) -> bool:
    """Return True if this Stripe event was already processed."""
    from src.db.models import WebhookEvent
    with SessionLocal() as s:
        return s.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first() is not None


def mark_webhook_seen(event_id: str, event_type: str, payload: str = "") -> None:
    from src.db.models import WebhookEvent
    with SessionLocal() as s:
        s.add(WebhookEvent(event_id=event_id, event_type=event_type, payload=payload[:2000]))
        s.commit()
