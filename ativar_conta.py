"""
Script para ativar conta admin no banco de dados local.
Execute: python ativar_conta.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.db.database import init_db, get_session, get_user_by_email, create_user
from src.db.models import User
from datetime import datetime, timezone, timedelta

EMAIL = "Business@globalhealthcareaccess.com"
SENHA = "PharmaIntel2026!"  # troque depois

init_db()

with get_session() as session:
    user = session.query(User).filter(User.email == EMAIL).first()

    if user:
        user.is_active       = True
        user.is_admin        = True
        user.plan            = "enterprise"
        user.period          = "monthly"
        user.subscription_status = "active"
        user.subscription_end    = datetime.now(timezone.utc) + timedelta(days=3650)
        user.password_hash   = User.hash_password(SENHA)
        session.commit()
        print(f"OK Conta atualizada: {EMAIL}")
    else:
        user = User(
            email            = EMAIL,
            password_hash    = User.hash_password(SENHA),
            full_name        = "Vinicius Figueiredo",
            plan             = "enterprise",
            period           = "monthly",
            is_active        = True,
            is_admin         = True,
            subscription_status = "active",
            subscription_end = datetime.now(timezone.utc) + timedelta(days=3650),
        )
        session.add(user)
        session.commit()
        print(f"OK Conta criada: {EMAIL}")

print(f"   Senha: {SENHA}")
print(f"   Plano: Enterprise")
print(f"   Admin: Sim")
print(f"\nATENCAO:  Troque a senha após o primeiro login.")
