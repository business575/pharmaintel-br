"""
stripe_products.py
==================
PharmaIntel BR — Cria produtos e preços no Stripe automaticamente.

Execução:
    python stripe_products.py

O script:
  1. Cria (ou reutiliza) os produtos no Stripe
  2. Cria os Price objects em BRL (recurring monthly)
  3. Imprime os Price IDs para colar no .env
  4. Opcionalmente atualiza o .env diretamente (--write-env)

Uso:
    python stripe_products.py
    python stripe_products.py --write-env
    python stripe_products.py --env-file .env.production
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    import stripe
except ImportError:
    print("ERRO: pacote 'stripe' não instalado.")
    print("Execute: pip install stripe")
    sys.exit(1)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

if not stripe.api_key or stripe.api_key.startswith("sk_live_your") or stripe.api_key.startswith("sk_test_your"):
    print("ERRO: STRIPE_SECRET_KEY não configurada no .env")
    print("Adicione sua chave Stripe ao arquivo .env antes de executar este script.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Definição dos produtos e preços
# ---------------------------------------------------------------------------

PRODUCTS = [
    {
        "env_key":   "STRIPE_PRICE_STARTER",
        "name":      "PharmaIntel BR — Starter",
        "statement": "PharmaIntel Starter",
        "description": (
            "1 usuário · 5 NCMs monitorados · Dashboard básico de importações "
            "farmacêuticas brasileiras (Comex Stat / ANVISA)"
        ),
        "amount":    29900,   # R$ 299,00 em centavos
        "currency":  "brl",
        "metadata":  {"tier": "starter", "seats": "1", "ncms": "5"},
        "features": [
            "Dashboard básico de importações",
            "5 NCMs monitorados",
            "Dados Comex Stat (Cap. 30 e 90)",
            "Histórico 12 meses",
            "Suporte por email",
        ],
    },
    {
        "env_key":   "STRIPE_PRICE_PRO",
        "name":      "PharmaIntel BR — Pro",
        "statement": "PharmaIntel Pro",
        "description": (
            "3 usuários · NCMs ilimitados · Alertas ANVISA · "
            "Agente IA farmacêutico (100 queries/mês) · ComprasNet"
        ),
        "amount":    69900,   # R$ 699,00
        "currency":  "brl",
        "metadata":  {"tier": "pro", "seats": "3", "ncms": "unlimited"},
        "features": [
            "3 usuários incluídos",
            "NCMs ilimitados",
            "Alertas ANVISA em tempo real",
            "Agente IA (100 queries/mês)",
            "ComprasNet — licitações públicas",
            "Comparativo anual",
            "Suporte prioritário",
        ],
    },
    {
        "env_key":   "STRIPE_PRICE_ENTERPRISE",
        "name":      "PharmaIntel BR — Enterprise",
        "statement": "PharmaIntel Enterprise",
        "description": (
            "10 usuários · Tudo do Pro · API REST · White-label · "
            "IA ilimitada · SLA · Suporte dedicado"
        ),
        "amount":    159900,  # R$ 1.599,00
        "currency":  "brl",
        "metadata":  {"tier": "enterprise", "seats": "10", "ncms": "unlimited"},
        "features": [
            "10 usuários incluídos",
            "Tudo do plano Pro",
            "API REST (acesso programático)",
            "White-label (marca própria)",
            "IA ilimitada",
            "SLA garantido",
            "Onboarding personalizado",
            "Suporte dedicado 24h",
        ],
    },
    {
        "env_key":   "STRIPE_PRICE_EXTRA_SEAT",
        "name":      "PharmaIntel BR — Usuário Adicional",
        "statement": "PharmaIntel +User",
        "description": "Usuário adicional para qualquer plano PharmaIntel BR",
        "amount":    9900,    # R$ 99,00
        "currency":  "brl",
        "metadata":  {"type": "addon", "addon": "extra_seat"},
        "features": ["1 usuário adicional"],
    },
]


# ---------------------------------------------------------------------------
# Funções de criação
# ---------------------------------------------------------------------------

def get_or_create_product(name: str, description: str, metadata: dict, features: list) -> str:
    """Retorna ID do produto existente ou cria um novo."""
    products = stripe.Product.search(query=f'name:"{name}"', limit=1)
    if products.data:
        product = products.data[0]
        print(f"  Produto existente: {product.id}  ({name})")
        return product.id

    product = stripe.Product.create(
        name=name,
        description=description,
        metadata=metadata,
        marketing_features=[{"name": f} for f in features],
    )
    print(f"  Produto criado: {product.id}  ({name})")
    return product.id


def get_or_create_price(
    product_id: str,
    amount: int,
    currency: str,
    statement_descriptor: str,
    metadata: dict,
) -> str:
    """Retorna ID do price existente (mesmo produto/valor) ou cria novo."""
    prices = stripe.Price.list(product=product_id, active=True, limit=10)
    for price in prices.data:
        if (
            price.unit_amount == amount
            and price.currency == currency
            and price.recurring
            and price.recurring.interval == "month"
        ):
            print(f"  Price existente: {price.id}  (R$ {amount/100:.2f}/mês)")
            return price.id

    price = stripe.Price.create(
        product=product_id,
        unit_amount=amount,
        currency=currency,
        recurring={"interval": "month"},
        metadata=metadata,
    )
    print(f"  Price criado: {price.id}  (R$ {amount/100:.2f}/mês)")
    return price.id


def update_env_file(env_file: Path, updates: dict) -> None:
    """Atualiza as variáveis no arquivo .env sem sobrescrever as outras."""
    content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""

    for key, value in updates.items():
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        replacement = f"{key}={value}"
        if pattern.search(content):
            content = pattern.sub(replacement, content)
        else:
            content += f"\n{replacement}"

    env_file.write_text(content, encoding="utf-8")
    print(f"\n.env atualizado: {env_file}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(write_env: bool = False, env_file: str = ".env") -> None:
    env_path = Path(env_file)

    print("=" * 60)
    print("PharmaIntel BR — Configuração Stripe")
    print(f"Modo: {'live' if 'live' in stripe.api_key else 'test'}")
    print("=" * 60)

    results: dict[str, str] = {}

    for product_def in PRODUCTS:
        print(f"\n{'─'*40}")
        print(f"Configurando: {product_def['name']}")

        product_id = get_or_create_product(
            product_def["name"],
            product_def["description"],
            product_def["metadata"],
            product_def["features"],
        )

        price_id = get_or_create_price(
            product_id,
            product_def["amount"],
            product_def["currency"],
            product_def["statement"],
            product_def["metadata"],
        )

        results[product_def["env_key"]] = price_id

    print("\n" + "=" * 60)
    print("PRICE IDs — adicione ao seu .env:")
    print("=" * 60)
    for key, price_id in results.items():
        print(f"{key}={price_id}")

    if write_env:
        update_env_file(env_path, results)
    else:
        print(f"\nPara atualizar o .env automaticamente, execute:")
        print(f"  python stripe_products.py --write-env")

    print("\n" + "=" * 60)
    print("Configure o webhook no painel Stripe:")
    print("  URL: https://seu-dominio.com/payments/webhook")
    print("  Eventos necessários:")
    events = [
        "checkout.session.completed",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_failed",
        "invoice.payment_succeeded",
        "customer.subscription.trial_will_end",
    ]
    for e in events:
        print(f"    + {e}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configura produtos Stripe para PharmaIntel BR")
    parser.add_argument("--write-env",  action="store_true", help="Atualiza .env com os Price IDs")
    parser.add_argument("--env-file",   default=".env",      help="Caminho do arquivo .env (padrão: .env)")
    args = parser.parse_args()
    main(write_env=args.write_env, env_file=args.env_file)
