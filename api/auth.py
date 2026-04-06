"""
api/auth.py
===========
PharmaIntel BR — API de Autenticação e Gestão de Usuários (FastAPI + JWT)

Endpoints
---------
  POST /auth/register         → cria empresa + usuário owner
  POST /auth/login            → retorna JWT access token
  POST /auth/refresh          → renova token (sliding window)
  GET  /auth/me               → retorna perfil do usuário autenticado
  POST /auth/invite           → convida usuário para a empresa (admin+)
  DELETE /auth/users/{id}     → remove usuário da empresa (owner)
  GET  /auth/company/users    → lista usuários da empresa
  POST /auth/change-password  → troca senha do usuário autenticado

JWT Payload
-----------
  sub        : user_id (int)
  company_id : int
  email      : str
  role       : str (owner|admin|member)
  tier       : str (none|starter|pro|enterprise)
  exp        : timestamp
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from database.crud import (
    authenticate_user,
    count_active_users,
    create_company,
    create_user,
    deactivate_user,
    get_company_users,
    get_subscription,
    get_user_by_email,
    get_user_by_id,
    seed_demo_accounts,
    update_user_password,
)
from database.models import User, get_db, init_db

load_dotenv()

# ---------------------------------------------------------------------------
# Configuração JWT
# ---------------------------------------------------------------------------
JWT_SECRET      = os.getenv("SESSION_SECRET_KEY", "pharmaintel_dev_secret_CHANGE_IN_PROD")
JWT_ALGORITHM   = "HS256"
ACCESS_TOKEN_TTL  = int(os.getenv("JWT_ACCESS_TTL_HOURS",  "24"))
REFRESH_TOKEN_TTL = int(os.getenv("JWT_REFRESH_TTL_DAYS",  "30"))

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/auth", tags=["Authentication"])
bearer = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    company_name: str
    email: str
    password: str
    full_name: str = ""
    cnpj: str = ""

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Senha deve ter pelo menos 6 caracteres")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class InviteRequest(BaseModel):
    email: str
    full_name: str = ""
    role: str = "member"
    password: str = "Mudar@123"   # temporária — usuário deve trocar


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Senha deve ter pelo menos 6 caracteres")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int   # segundos
    user: dict


# ---------------------------------------------------------------------------
# Helpers JWT
# ---------------------------------------------------------------------------

def create_access_token(user: User, tier: str) -> str:
    payload = {
        "sub":        str(user.id),
        "company_id": user.company_id,
        "email":      user.email,
        "role":       user.role,
        "tier":       tier,
        "exp":        datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_TTL),
        "iat":        datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decodifica e valida um JWT. Lança HTTPException se inválido/expirado."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado. Faça login novamente.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")


def decode_token_safe(token: str) -> Optional[dict]:
    """Versão que não lança exceção — para uso no Streamlit."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: extrai e valida o usuário autenticado do JWT."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token de autenticação necessário.")
    payload = decode_token(credentials.credentials)
    user = get_user_by_id(db, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuário inativo ou não encontrado.")
    return user


def require_role(*roles: str):
    """Dependency factory: exige um dos roles listados."""
    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Permissão insuficiente. Requerido: {', '.join(roles)}"
            )
        return user
    return _checker


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    Registra uma nova empresa e seu usuário owner.
    Cria assinatura 'none' (sem plano ativo).
    """
    if get_user_by_email(db, req.email):
        raise HTTPException(
            status_code=409,
            detail="Email já cadastrado. Use outro email ou faça login."
        )

    company = create_company(db, req.company_name.strip(), req.cnpj.strip() or None)
    user    = create_user(db, company.id, req.email, req.password,
                          req.full_name, role="owner")
    db.commit()
    db.refresh(user)

    tier  = "none"
    token = create_access_token(user, tier)

    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_TTL * 3600,
        user=_user_dict(user, tier),
    )


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Autentica email/senha e retorna JWT."""
    user = authenticate_user(db, req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Email ou senha incorretos."
        )
    db.commit()  # salva last_login

    sub  = get_subscription(db, user.company_id)
    tier = sub.tier if (sub and sub.is_active) else "none"
    token = create_access_token(user, tier)

    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_TTL * 3600,
        user=_user_dict(user, tier),
    )


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retorna perfil completo do usuário autenticado."""
    sub  = get_subscription(db, current_user.company_id)
    tier = sub.tier if (sub and sub.is_active) else "none"

    seat_count = count_active_users(db, current_user.company_id)
    total_seats = sub.total_seats if sub else 1

    return {
        "user": _user_dict(current_user, tier),
        "company": {
            "id":   current_user.company.id,
            "name": current_user.company.name,
            "slug": current_user.company.slug,
        },
        "subscription": _sub_dict(sub) if sub else None,
        "seats": {"used": seat_count, "total": total_seats},
    }


@router.post("/invite", status_code=201)
def invite_user(
    req: InviteRequest,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Convida um novo usuário para a empresa (somente owner/admin)."""
    sub = get_subscription(db, current_user.company_id)
    if not sub or not sub.is_active:
        raise HTTPException(
            status_code=402,
            detail="Empresa sem assinatura ativa. Assine um plano para adicionar usuários."
        )

    used  = count_active_users(db, current_user.company_id)
    total = sub.total_seats
    if used >= total:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Limite de {total} usuário(s) atingido para o plano {sub.tier.title()}. "
                "Adicione seats extras ou faça upgrade."
            )
        )

    if get_user_by_email(db, req.email):
        raise HTTPException(status_code=409, detail="Email já cadastrado.")

    if req.role == "owner":
        raise HTTPException(status_code=400, detail="Não é possível convidar outro owner.")

    new_user = create_user(
        db, current_user.company_id, req.email,
        req.password, req.full_name, req.role,
    )
    db.commit()
    db.refresh(new_user)

    return {
        "message": f"Usuário {req.email} adicionado com sucesso.",
        "user_id": new_user.id,
    }


@router.get("/company/users")
def list_company_users(
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db),
):
    """Lista todos os usuários ativos da empresa."""
    users = get_company_users(db, current_user.company_id)
    sub   = get_subscription(db, current_user.company_id)
    return {
        "users":       [_user_dict(u, "") for u in users],
        "total_seats": sub.total_seats if sub else 1,
        "used_seats":  len(users),
    }


@router.delete("/users/{user_id}", status_code=200)
def remove_user(
    user_id: int,
    current_user: User = Depends(require_role("owner")),
    db: Session = Depends(get_db),
):
    """Remove (desativa) usuário da empresa. Somente owner."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Não é possível remover a si mesmo.")
    target = get_user_by_id(db, user_id)
    if not target or target.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    deactivate_user(db, user_id)
    db.commit()
    return {"message": "Usuário removido."}


@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Troca a senha do usuário autenticado."""
    from database.crud import _verify_pw
    if not _verify_pw(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")
    update_user_password(db, current_user, req.new_password)
    db.commit()
    return {"message": "Senha alterada com sucesso."}


# ---------------------------------------------------------------------------
# Helpers de serialização
# ---------------------------------------------------------------------------

def _user_dict(user: User, tier: str) -> dict:
    return {
        "id":         user.id,
        "email":      user.email,
        "full_name":  user.full_name or "",
        "role":       user.role,
        "company_id": user.company_id,
        "tier":       tier,
        "is_active":  user.is_active,
    }


def _sub_dict(sub) -> dict:
    return {
        "tier":                sub.tier,
        "status":              sub.status,
        "seats_included":      sub.seats_included,
        "extra_seats":         sub.extra_seats,
        "total_seats":         sub.total_seats,
        "ncm_limit":           sub.ncm_limit,
        "ai_queries_limit":    sub.ai_queries_limit,
        "ai_queries_used":     sub.ai_queries_used,
        "current_period_end":  sub.current_period_end.isoformat() if sub.current_period_end else None,
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


# ---------------------------------------------------------------------------
# Startup: garante tabelas + seeds demo
# ---------------------------------------------------------------------------

def startup_auth(db_session_factory):
    """Chamado no lifespan do FastAPI: init DB + seeds."""
    init_db()
    with db_session_factory() as db:
        n = seed_demo_accounts(db)
        if n:
            import logging
            logging.getLogger(__name__).info("Contas demo criadas: %d", n)
