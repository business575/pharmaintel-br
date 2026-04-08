"""
models.py
=========
PharmaIntel BR — SQLAlchemy ORM models.

Tables:
    users         → subscriber accounts
    subscriptions → Stripe subscription records
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase

TRIAL_DAYS = 7


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    password_hash   = Column(String(255), nullable=False)
    full_name       = Column(String(255), default="")
    plan            = Column(String(50), default="")       # starter | pro | enterprise
    period          = Column(String(20), default="")       # monthly | quarterly | biannual | annual
    is_active       = Column(Boolean, default=False)
    is_admin        = Column(Boolean, default=False)
    stripe_customer_id    = Column(String(100), default="")
    stripe_subscription_id = Column(String(100), default="")
    subscription_status   = Column(String(50), default="")  # active | canceled | past_due | trialing
    subscription_end      = Column(DateTime, nullable=True)
    is_trial        = Column(Boolean, default=False)
    trial_start     = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def check_password(self, password: str) -> bool:
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def generate_password(length: int = 12) -> str:
        alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @property
    def trial_days_remaining(self) -> int:
        """Days left in free trial. Returns 0 if not a trial or expired."""
        if not self.is_trial or not self.trial_start:
            return 0
        start = self.trial_start.replace(tzinfo=timezone.utc) if self.trial_start.tzinfo is None else self.trial_start
        elapsed = (datetime.now(timezone.utc) - start).days
        return max(0, TRIAL_DAYS - elapsed)

    @property
    def has_active_subscription(self) -> bool:
        if not self.is_active:
            return False
        if self.is_trial:
            return self.trial_days_remaining > 0
        if self.subscription_status not in ("active", "trialing"):
            return False
        if self.subscription_end and datetime.now(timezone.utc) > self.subscription_end.replace(tzinfo=timezone.utc):
            return False
        return True


class DemoLead(Base):
    """Demo leads captured from the free AI demo."""
    __tablename__ = "demo_leads"

    id             = Column(Integer, primary_key=True)
    email          = Column(String(255), unique=True, nullable=False, index=True)
    lang           = Column(String(5), default="PT")
    status         = Column(String(30), default="new")        # new|demo_tested|contacted|subscribed|lost
    temperature    = Column(String(10), default="cold")       # hot|warm|cold
    questions_asked = Column(Integer, default=0)
    country_hint   = Column(String(100), default="")
    notes          = Column(Text, default="")
    follow_up_count = Column(Integer, default=0)
    emails_sent    = Column(Text, default="[]")               # JSON list of days sent
    last_contact   = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))


class WebhookEvent(Base):
    """Log of processed Stripe webhook events to prevent duplicates."""
    __tablename__ = "webhook_events"

    id          = Column(Integer, primary_key=True)
    event_id    = Column(String(100), unique=True, nullable=False)
    event_type  = Column(String(100), nullable=False)
    processed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    payload     = Column(Text, default="")
