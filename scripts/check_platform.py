"""
check_platform.py — Uptime check para pharmaceuticaai.com / pharmaintel-br.onrender.com

Por que existe: o monitor anterior gerava centenas de drafts "FORA DO AR" em
Gmail porque rodava em sandbox com egresso restrito — toda requisição retornava
HTTP 403 com `x-deny-reason: host_not_allowed` (resposta do PROXY do sandbox,
não do servidor real).

Este script:
1. Faz GET direto sobre o host.
2. Diferencia "bloqueio do sandbox" (header x-deny-reason) de "downtime real".
3. Só sinaliza FORA DO AR quando a resposta vier do próprio servidor.

Uso:
    python scripts/check_platform.py
    python scripts/check_platform.py --json

Exit codes:
    0 = up
    1 = down (real)
    2 = inconclusivo (sandbox bloqueou o egresso — não é falha do produto)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import httpx

HOSTS = [
    "https://pharmaceuticaai.com/",
    "https://pharmaintel-br.onrender.com/",
]

SANDBOX_BLOCK_HEADER = "x-deny-reason"
SANDBOX_BLOCK_VALUE = "host_not_allowed"


def check_one(url: str, timeout: float = 15.0) -> dict:
    result = {
        "url": url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status_code": None,
        "verdict": None,
        "reason": None,
    }
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        result["status_code"] = r.status_code
        deny = r.headers.get(SANDBOX_BLOCK_HEADER, "").lower()

        if deny == SANDBOX_BLOCK_VALUE:
            result["verdict"] = "inconclusive"
            result["reason"] = (
                "Egresso do sandbox bloqueou o host. "
                "Adicione o domínio ao allowlist do ambiente — não é falha do produto."
            )
        elif 200 <= r.status_code < 400:
            result["verdict"] = "up"
            result["reason"] = f"HTTP {r.status_code}"
        else:
            result["verdict"] = "down"
            result["reason"] = f"HTTP {r.status_code} retornado pelo servidor"
    except httpx.RequestError as exc:
        result["verdict"] = "inconclusive"
        result["reason"] = f"network error: {type(exc).__name__}: {exc}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = [check_one(u) for u in HOSTS]

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            print(f"{r['verdict'].upper():<13} {r['url']} — {r['reason']}")

    if any(r["verdict"] == "down" for r in results):
        return 1
    if all(r["verdict"] == "up" for r in results):
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
