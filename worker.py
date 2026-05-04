"""
worker.py — PharmaIntel BR Sales Worker

Roda uma vez por execução (Railway Cron Job dispara diariamente às 09:00 BRT).

Ciclo completo:
  1. Outreach — envia emails para prospects pendentes no banco (outreach_agent)
  2. ANVISA scan — busca novas empresas no ANVISA, enriquece via ReceitaWS, envia (autonomous_sales_agent)
  3. Follow-ups — reengaja leads sem resposta após 3 dias
  4. Relatório — imprime resumo do ciclo para logs do Railway
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("worker")

RESEND_KEY = os.getenv("RESEND_API_KEY", "")
GROQ_KEY   = os.getenv("GROQ_API_KEY", "")


def _check_env() -> bool:
    missing = []
    if not RESEND_KEY:
        missing.append("RESEND_API_KEY")
    if not GROQ_KEY:
        missing.append("GROQ_API_KEY")
    if missing:
        logger.error("Variáveis de ambiente ausentes: %s — worker abortado.", ", ".join(missing))
        return False
    return True


# ---------------------------------------------------------------------------
# Step 1 — Outreach (prospects no banco de dados)
# ---------------------------------------------------------------------------

def step_outreach() -> dict:
    logger.info("=== STEP 1: Outreach (prospects DB) ===")
    try:
        from src.agents.outreach_agent import run_daily_outreach
        result = run_daily_outreach(daily_limit=20)
        logger.info("Outreach: %d enviados, %d erros", result["sent"], result["failed"])
        return result
    except Exception as exc:
        logger.error("Outreach falhou: %s", exc)
        return {"sent": 0, "failed": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Step 2 — ANVISA scan (autonomous agent — novas empresas)
# ---------------------------------------------------------------------------

def step_anvisa_scan() -> dict:
    logger.info("=== STEP 2: ANVISA scan (novas empresas) ===")
    try:
        from src.agents.autonomous_sales_agent import run_daily_agent
        result = run_daily_agent(dry_run=False)
        logger.info(
            "ANVISA scan: %d novos enviados, %d follow-ups, %d erros",
            result["novos_enviados"],
            result["followups_enviados"],
            result["erros"],
        )
        return result
    except Exception as exc:
        logger.error("ANVISA scan falhou: %s", exc)
        return {"novos_enviados": 0, "followups_enviados": 0, "erros": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Step 3 — Relatório final
# ---------------------------------------------------------------------------

def print_report(outreach: dict, anvisa: dict) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_sent = outreach.get("sent", 0) + anvisa.get("novos_enviados", 0)
    total_followups = anvisa.get("followups_enviados", 0)
    total_errors = outreach.get("failed", 0) + anvisa.get("erros", 0)

    report = {
        "timestamp": now,
        "emails_enviados": total_sent,
        "followups_enviados": total_followups,
        "erros": total_errors,
        "outreach_db": {"enviados": outreach.get("sent", 0), "erros": outreach.get("failed", 0)},
        "anvisa_scan": {
            "novos": anvisa.get("novos_enviados", 0),
            "followups": anvisa.get("followups_enviados", 0),
            "erros": anvisa.get("erros", 0),
        },
    }

    logger.info("=== RELATÓRIO DIÁRIO ===")
    logger.info(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("Worker PharmaIntel BR iniciado — %s", datetime.now(timezone.utc).isoformat())

    if not _check_env():
        sys.exit(1)

    outreach_result = step_outreach()
    anvisa_result   = step_anvisa_scan()
    print_report(outreach_result, anvisa_result)

    logger.info("Worker concluído.")


if __name__ == "__main__":
    main()
