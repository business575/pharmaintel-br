"""
database/crud.py
================
Operações CRUD reutilizáveis — usadas por auth.py, payments.py e billing.py.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Company, Subscription, UsageLog, User

# ---------------------------------------------------------------------------
# Constantes de plano
# ---------------------------------------------------------------------------

TIER_DEFAULTS = {
    "starter": {
        "seats_included":    1,
        "ncm_limit":         5,
        "ai_queries_limit":  0,     # sem IA
    },
    "pro": {
        "seats_included":    3,
        "ncm_limit":        -1,     # ilimitado
        "ai_queries_limit": 100,    # 100/mês
    },
    "enterprise": {
        "seats_included":   10,
        "ncm_limit":        -1,
        "ai_queries_limit": -1,     # ilimitado
    },
}

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _hash_pw(password: str) -> str:
    """SHA-256 hash para MVP. Em produção, usar bcrypt ou argon2."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_pw(password: str, hashed: str) -> bool:
    return _hash_pw(password) == hashed


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
    return slug[:50]


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug = base
    i = 2
    while db.query(Company).filter(Company.slug == slug).first():
        slug = f"{base}-{i}"
        i += 1
    return slug


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

def get_company_by_id(db: Session, company_id: int) -> Optional[Company]:
    return db.query(Company).filter(Company.id == company_id).first()


def get_company_by_slug(db: Session, slug: str) -> Optional[Company]:
    return db.query(Company).filter(Company.slug == slug).first()


def get_company_by_stripe_customer(db: Session, customer_id: str) -> Optional[Company]:
    return db.query(Company).filter(Company.stripe_customer_id == customer_id).first()


def create_company(db: Session, name: str, cnpj: str = None) -> Company:
    slug = _unique_slug(db, name)
    company = Company(name=name, slug=slug, cnpj=cnpj)
    db.add(company)
    db.flush()  # gera o id
    # Cria assinatura vazia
    sub = Subscription(company_id=company.id, tier="none", status="none")
    db.add(sub)
    return company


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.strip().lower()).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_company_users(db: Session, company_id: int) -> list[User]:
    return db.query(User).filter(User.company_id == company_id, User.is_active == True).all()


def count_active_users(db: Session, company_id: int) -> int:
    return db.query(User).filter(User.company_id == company_id, User.is_active == True).count()


def create_user(
    db: Session,
    company_id: int,
    email: str,
    password: str,
    full_name: str = "",
    role: str = "member",
) -> User:
    user = User(
        company_id=company_id,
        email=email.strip().lower(),
        password_hash=_hash_pw(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = get_user_by_email(db, email)
    if not user or not user.is_active:
        return None
    if not _verify_pw(password, user.password_hash):
        return None
    # Atualiza last_login
    user.last_login = datetime.now(timezone.utc)
    return user


def update_user_password(db: Session, user: User, new_password: str) -> None:
    user.password_hash = _hash_pw(new_password)


def deactivate_user(db: Session, user_id: int) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    user.is_active = False
    return True


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

def get_subscription(db: Session, company_id: int) -> Optional[Subscription]:
    return db.query(Subscription).filter(Subscription.company_id == company_id).first()


def get_subscription_by_stripe_id(db: Session, stripe_sub_id: str) -> Optional[Subscription]:
    return db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_sub_id
    ).first()


def activate_subscription(
    db: Session,
    company_id: int,
    tier: str,
    stripe_subscription_id: str,
    stripe_customer_id: str,
    stripe_price_id: str,
    period_start: datetime,
    period_end: datetime,
    extra_seats: int = 0,
) -> Subscription:
    defaults = TIER_DEFAULTS.get(tier, TIER_DEFAULTS["starter"])

    sub = get_subscription(db, company_id)
    if not sub:
        sub = Subscription(company_id=company_id)
        db.add(sub)

    sub.tier                     = tier
    sub.status                   = "active"
    sub.stripe_subscription_id   = stripe_subscription_id
    sub.stripe_customer_id       = stripe_customer_id
    sub.stripe_price_id          = stripe_price_id
    sub.seats_included           = defaults["seats_included"]
    sub.extra_seats              = extra_seats
    sub.ncm_limit                = defaults["ncm_limit"]
    sub.ai_queries_limit         = defaults["ai_queries_limit"]
    sub.ai_queries_used          = 0
    sub.ai_quota_reset_at        = period_end
    sub.current_period_start     = period_start
    sub.current_period_end       = period_end
    sub.cancel_at_period_end     = False
    sub.canceled_at              = None
    return sub


def update_subscription_status(
    db: Session,
    stripe_sub_id: str,
    status: str,
    period_end: datetime = None,
    cancel_at_period_end: bool = False,
) -> Optional[Subscription]:
    sub = get_subscription_by_stripe_id(db, stripe_sub_id)
    if not sub:
        return None
    sub.status = status
    if period_end:
        sub.current_period_end = period_end
    sub.cancel_at_period_end = cancel_at_period_end
    return sub


def cancel_subscription(db: Session, stripe_sub_id: str) -> Optional[Subscription]:
    sub = get_subscription_by_stripe_id(db, stripe_sub_id)
    if not sub:
        return None
    sub.status      = "canceled"
    sub.tier        = "none"
    sub.canceled_at = datetime.now(timezone.utc)
    return sub


def add_extra_seats(db: Session, company_id: int, seats: int) -> Optional[Subscription]:
    sub = get_subscription(db, company_id)
    if not sub:
        return None
    sub.extra_seats += seats
    return sub


def reset_ai_quota_if_needed(db: Session, sub: Subscription) -> None:
    """Reseta contador de AI queries se o período já virou."""
    now = datetime.now(timezone.utc)
    reset_at = sub.ai_quota_reset_at
    if reset_at and now > reset_at.replace(tzinfo=timezone.utc):
        sub.ai_queries_used   = 0
        sub.ai_quota_reset_at = now + timedelta(days=30)


def increment_ai_usage(db: Session, sub: Subscription) -> bool:
    """
    Incrementa contador de AI queries. Retorna False se limite atingido.
    """
    reset_ai_quota_if_needed(db, sub)
    if sub.ai_queries_limit == -1:   # ilimitado
        sub.ai_queries_used += 1
        return True
    if sub.ai_queries_used >= sub.ai_queries_limit:
        return False
    sub.ai_queries_used += 1
    return True


# ---------------------------------------------------------------------------
# Usage Logs
# ---------------------------------------------------------------------------

def log_usage(
    db: Session,
    company_id: int,
    feature: str,
    user_id: int = None,
    metadata: dict = None,
) -> UsageLog:
    log = UsageLog(
        company_id=company_id,
        user_id=user_id,
        feature=feature,
        log_data=json.dumps(metadata, ensure_ascii=False) if metadata else None,
    )
    db.add(log)
    return log


def get_usage_count(
    db: Session,
    company_id: int,
    feature: str,
    since: datetime = None,
) -> int:
    q = db.query(UsageLog).filter(
        UsageLog.company_id == company_id,
        UsageLog.feature == feature,
    )
    if since:
        q = q.filter(UsageLog.created_at >= since)
    return q.count()


# ---------------------------------------------------------------------------
# Bootstrap — cria contas demo se DB estiver vazio
# ---------------------------------------------------------------------------

DEMO_ACCOUNTS = [
    {
        "company": "Demo Starter Ltda",
        "cnpj": "00.000.000/0001-01",
        "email": "starter@pharmaintel.com.br",
        "password": "demo123",
        "full_name": "Demo Starter",
        "role": "owner",
        "tier": "starter",
    },
    {
        "company": "Demo Pro Farmacêutica",
        "cnpj": "00.000.000/0001-02",
        "email": "demo@pharmaintel.com.br",
        "password": "demo123",
        "full_name": "Demo Pro",
        "role": "owner",
        "tier": "pro",
    },
    {
        "company": "Demo Enterprise S/A",
        "cnpj": "00.000.000/0001-03",
        "email": "enterprise@pharmaintel.com.br",
        "password": "demo123",
        "full_name": "Demo Enterprise",
        "role": "owner",
        "tier": "enterprise",
    },
]


def seed_demo_accounts(db: Session) -> int:
    """Cria contas demo se não existirem. Retorna nº criadas."""
    created = 0
    for acc in DEMO_ACCOUNTS:
        if get_user_by_email(db, acc["email"]):
            continue
        company = create_company(db, acc["company"], acc["cnpj"])
        create_user(db, company.id, acc["email"], acc["password"],
                    acc["full_name"], acc["role"])
        defaults = TIER_DEFAULTS.get(acc["tier"], {})
        sub = get_subscription(db, company.id)
        if sub:
            sub.tier               = acc["tier"]
            sub.status             = "active"
            sub.seats_included     = defaults.get("seats_included", 1)
            sub.ncm_limit          = defaults.get("ncm_limit", 5)
            sub.ai_queries_limit   = defaults.get("ai_queries_limit", 0)
            sub.current_period_end = datetime(2099, 12, 31, tzinfo=timezone.utc)
            sub.ai_quota_reset_at  = datetime(2099, 12, 31, tzinfo=timezone.utc)
        created += 1
    return created
