"""
api/main.py
===========
PharmaIntel BR — FastAPI backend.

Execução:
    uvicorn api.main:app --reload --port 8000

Endpoints:
    GET  /health           → Health check
    POST /etl/run          → Trigger ETL pipeline
    GET  /data/kpis        → KPIs anuais
    GET  /data/top-ncm     → Ranking NCMs
    GET  /data/top-paises  → Ranking países
    POST /agent/chat       → Groq AI agent
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PharmaIntel BR API starting up...")
    # Ensure database tables exist
    try:
        from src.db.database import init_db
        init_db()
        logger.info("Database initialized.")
    except Exception as exc:
        logger.warning("DB init failed: %s", exc)
    yield
    logger.info("PharmaIntel BR API shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PharmaIntel BR — API",
    description="Backend de dados e IA para inteligência farmacêutica",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://localhost:8000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ETLRequest(BaseModel):
    year: int = 2024
    force_refresh: bool = False


class ChatRequest(BaseModel):
    message: str
    year: int = 2024
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# State (simple in-memory agent pool)
# ---------------------------------------------------------------------------
_agent_pool: dict = {}


def _get_agent(year: int):
    from src.agents.pharma_agent import PharmaAgent
    if year not in _agent_pool:
        _agent_pool[year] = PharmaAgent(year=year)
    return _agent_pool[year]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "PharmaIntel BR API", "version": "2.0.0"}


@app.post("/etl/run")
async def run_etl(req: ETLRequest, background_tasks: BackgroundTasks):
    """Trigger the 5-stage ETL pipeline (runs in background)."""
    from src.utils.etl_pipeline import run_pipeline

    def _run():
        result = run_pipeline(year=req.year, force_refresh=req.force_refresh)
        logger.info("ETL completed: %s", result.summary())

    background_tasks.add_task(_run)
    return {"message": f"ETL started for year {req.year}", "status": "running"}


@app.get("/data/kpis")
def get_kpis(year: int = 2024):
    """Return annual KPIs from processed data."""
    import pandas as pd
    PROCESSED = ROOT / "data" / "processed"
    path = PROCESSED / f"kpis_anuais_{year}.parquet"
    if not path.exists():
        raise HTTPException(404, detail=f"KPIs for {year} not found. Run /etl/run first.")
    df = pd.read_parquet(path)
    return df.to_dict(orient="records")


@app.get("/data/top-ncm")
def get_top_ncm(year: int = 2024, top_n: int = 20):
    """Return top NCMs by FOB value."""
    import pandas as pd
    PROCESSED = ROOT / "data" / "processed"
    path = PROCESSED / f"top_ncm_{year}.parquet"
    if not path.exists():
        raise HTTPException(404, detail=f"Top NCM data for {year} not found.")
    df = pd.read_parquet(path).head(top_n)
    return df.to_dict(orient="records")


@app.get("/data/top-paises")
def get_top_paises(year: int = 2024, top_n: int = 15):
    """Return top countries by FOB value."""
    import pandas as pd
    PROCESSED = ROOT / "data" / "processed"
    path = PROCESSED / f"top_paises_{year}.parquet"
    if not path.exists():
        raise HTTPException(404, detail=f"Top countries data for {year} not found.")
    df = pd.read_parquet(path).head(top_n)
    return df.to_dict(orient="records")


@app.get("/data/comtrade")
def get_comtrade(year: int = 2024):
    """Return UN Comtrade data for Brazil."""
    import pandas as pd
    PROCESSED = ROOT / "data" / "processed"
    path = PROCESSED / f"comtrade_{year}.parquet"
    if not path.exists():
        raise HTTPException(404, detail=f"Comtrade data for {year} not found.")
    df = pd.read_parquet(path)
    return df.to_dict(orient="records")


@app.post("/agent/chat")
def agent_chat(req: ChatRequest):
    """Send a message to the PharmaIntel AI agent."""
    agent = _get_agent(req.year)
    response = agent.chat(req.message)
    return {
        "text": response.text,
        "tool_calls": response.tool_calls_made,
        "tokens_used": response.tokens_used,
        "error": response.error,
    }


@app.post("/agent/reset")
def agent_reset(year: int = 2024):
    """Reset the agent conversation history."""
    if year in _agent_pool:
        _agent_pool[year].reset()
    return {"message": f"Agent for year {year} reset."}


# ---------------------------------------------------------------------------
# Stripe Webhook
# ---------------------------------------------------------------------------

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    """
    Handle Stripe webhook events for subscription lifecycle management.

    Configure in Stripe Dashboard → Webhooks → Add endpoint:
        URL: https://<your-api-domain>/stripe/webhook
        Events: customer.subscription.*, invoice.payment_*
    """
    from datetime import datetime, timezone

    payload = await request.body()

    try:
        from src.payments.stripe_client import construct_webhook_event
        event = construct_webhook_event(payload, stripe_signature or "")
    except Exception as exc:
        logger.warning("Webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"Webhook error: {exc}")

    event_id   = event.get("id", "")
    event_type = event.get("type", "")

    # Idempotency check
    from src.db.database import webhook_seen, mark_webhook_seen
    if webhook_seen(event_id):
        return JSONResponse({"status": "already_processed"})

    logger.info("Stripe event: %s (%s)", event_type, event_id)

    try:
        data_obj = event.get("data", {}).get("object", {})

        if event_type in ("customer.subscription.created", "customer.subscription.updated"):
            _handle_subscription_update(data_obj)

        elif event_type == "customer.subscription.deleted":
            _handle_subscription_canceled(data_obj)

        elif event_type == "invoice.payment_failed":
            _handle_payment_failed(data_obj)

        mark_webhook_seen(event_id, event_type, str(event)[:2000])

    except Exception as exc:
        logger.error("Webhook handling error for %s: %s", event_type, exc)
        # Return 200 to prevent Stripe retries for our own errors
        return JSONResponse({"status": "error", "detail": str(exc)})

    return JSONResponse({"status": "ok"})


def _handle_subscription_update(sub: dict) -> None:
    from datetime import datetime, timezone
    from src.db.database import update_subscription

    customer_id = sub.get("customer", "")
    sub_id      = sub.get("id", "")
    status      = sub.get("status", "")
    meta        = sub.get("metadata") or {}
    plan        = meta.get("plan", "")
    period      = meta.get("period", "")

    # current_period_end is a Unix timestamp
    period_end_ts = sub.get("current_period_end")
    period_end    = datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None

    updated = update_subscription(
        stripe_customer_id=customer_id,
        subscription_id=sub_id,
        status=status,
        plan=plan,
        period=period,
        subscription_end=period_end,
    )
    logger.info("Subscription updated (customer=%s, status=%s, found=%s)", customer_id, status, updated)


def _handle_subscription_canceled(sub: dict) -> None:
    from src.db.database import update_subscription
    customer_id = sub.get("customer", "")
    sub_id      = sub.get("id", "")
    update_subscription(customer_id, sub_id, "canceled")
    logger.info("Subscription canceled (customer=%s)", customer_id)


def _handle_payment_failed(invoice: dict) -> None:
    from src.db.database import update_subscription
    customer_id = invoice.get("customer", "")
    sub_id      = invoice.get("subscription", "")
    if customer_id:
        update_subscription(customer_id, sub_id, "past_due")
    logger.info("Payment failed (customer=%s)", customer_id)
