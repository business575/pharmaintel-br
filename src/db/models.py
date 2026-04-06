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
    def has_active_subscription(self) -> bool:
        if not self.is_active:
            return False
        if self.subscription_status not in ("active", "trialing"):
            return False
        if self.subscription_end and datetime.now(timezone.utc) > self.subscription_end.replace(tzinfo=timezone.utc):
            return False
        return True


class WebhookEvent(Base):
    """Log of processed Stripe webhook events to prevent duplicates."""
    __tablename__ = "webhook_events"

    id          = Column(Integer, primary_key=True)
    event_id    = Column(String(100), unique=True, nullable=False)
    event_type  = Column(String(100), nullable=False)
    processed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    payload     = Column(Text, default="")
