"""
database/models.py
==================
PharmaIntel BR — Modelos SQLAlchemy (SQLite para MVP, PostgreSQL-ready)

Tabelas
-------
  companies     → tenants multi-empresa
  users         → usuários por empresa (com roles)
  subscriptions → plano ativo, tier, seats, period
  usage_logs    → rastreamento de consumo por feature (AI queries, NCMs, API calls)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

# ---------------------------------------------------------------------------
# Engine — SQLite para MVP, troca por DATABASE_URL em produção
# ---------------------------------------------------------------------------
_DB_FILE = Path(__file__).resolve().parents[1] / "data" / "pharmaintel.db"
_DB_FILE.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DB_FILE}")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Base declarativa
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class Company(Base):
    """
    Tenant — representa uma empresa cliente (multi-tenant).
    Cada empresa tem sua assinatura e seus usuários.
    """
    __tablename__ = "companies"

    id                 = Column(Integer, primary_key=True, index=True)
    name               = Column(String(255), nullable=False)
    slug               = Column(String(100), unique=True, nullable=False, index=True)
    cnpj               = Column(String(18), nullable=True)          # CNPJ formatado
    stripe_customer_id = Column(String(100), unique=True, nullable=True)
    is_active          = Column(Boolean, default=True, nullable=False)
    created_at         = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at         = Column(DateTime,
                                default=lambda: datetime.now(timezone.utc),
                                onupdate=lambda: datetime.now(timezone.utc))

    # Relacionamentos
    users        = relationship("User",         back_populates="company", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="company", uselist=False, cascade="all, delete-orphan")
    usage_logs   = relationship("UsageLog",     back_populates="company", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Company id={self.id} slug={self.slug!r}>"


class User(Base):
    """
    Usuário de uma empresa. Role define permissões dentro do tenant.
    """
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id            = Column(Integer, primary_key=True, index=True)
    company_id    = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    email         = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name     = Column(String(255), nullable=True)
    role          = Column(String(20),  nullable=False, default="member")
    # roles: owner (1 per company), admin, member
    is_active     = Column(Boolean, default=True,  nullable=False)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login    = Column(DateTime, nullable=True)

    # Relacionamentos
    company    = relationship("Company",  back_populates="users")
    usage_logs = relationship("UsageLog", back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"


class Subscription(Base):
    """
    Assinatura ativa da empresa.
    Um registro por empresa (upsert on webhook).
    """
    __tablename__ = "subscriptions"

    id                     = Column(Integer, primary_key=True, index=True)
    company_id             = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"),
                                    unique=True, nullable=False, index=True)
    stripe_subscription_id = Column(String(100), unique=True, nullable=True)
    stripe_customer_id     = Column(String(100), nullable=True)
    stripe_price_id        = Column(String(100), nullable=True)

    # Plano
    tier           = Column(String(20),  nullable=False, default="none")
    # tiers: none, starter, pro, enterprise
    status         = Column(String(20),  nullable=False, default="none")
    # statuses: none, trialing, active, past_due, canceled, unpaid

    # Seats
    seats_included = Column(Integer, default=1,  nullable=False)
    extra_seats    = Column(Integer, default=0,  nullable=False)

    # AI quota
    ai_queries_limit   = Column(Integer, default=0,  nullable=False)   # -1 = unlimited
    ai_queries_used    = Column(Integer, default=0,  nullable=False)
    ai_quota_reset_at  = Column(DateTime, nullable=True)               # resets monthly

    # NCM monitoring
    ncm_limit          = Column(Integer, default=5,  nullable=False)   # -1 = unlimited

    # Billing period
    current_period_start = Column(DateTime, nullable=True)
    current_period_end   = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    canceled_at          = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relacionamento
    company = relationship("Company", back_populates="subscription")

    @property
    def total_seats(self) -> int:
        return self.seats_included + self.extra_seats

    @property
    def is_active(self) -> bool:
        return self.status in ("active", "trialing")

    @property
    def ai_unlimited(self) -> bool:
        return self.ai_queries_limit == -1

    def __repr__(self) -> str:
        return f"<Subscription company_id={self.company_id} tier={self.tier!r} status={self.status!r}>"


class UsageLog(Base):
    """
    Log de uso de features por empresa/usuário.
    Usado para: AI queries, API calls, NCM accesses.
    """
    __tablename__ = "usage_logs"

    id         = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(Integer, ForeignKey("users.id",    ondelete="SET NULL"), nullable=True,  index=True)
    feature    = Column(String(50), nullable=False, index=True)
    # features: ai_query, api_call, ncm_monitor, etl_run, export
    log_data   = Column(Text, nullable=True)   # JSON serializado
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relacionamentos
    company = relationship("Company", back_populates="usage_logs")
    user    = relationship("User",    back_populates="usage_logs")

    def __repr__(self) -> str:
        return f"<UsageLog company_id={self.company_id} feature={self.feature!r}>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db():
    """Dependency injector para FastAPI (context manager de sessão)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session():
    """Context manager para uso fora do FastAPI (ex: Streamlit, scripts)."""
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Cria todas as tabelas se não existirem (idempotente)."""
    Base.metadata.create_all(bind=engine)
