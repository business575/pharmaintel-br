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
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
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
