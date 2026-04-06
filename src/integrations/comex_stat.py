"""
comex_stat.py
=============
Integração com a API Comex Stat (MDIC) — dados de importação farmacêutica.

Fonte: https://api-comexstat.mdic.gov.br
Cobertura: Capítulo 30 (medicamentos) e Capítulo 90 (dispositivos médicos)

Nota: SSL verify=False necessário em ambiente Windows com certificado corporativo.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import urllib3
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
BASE_URL = "https://api-comexstat.mdic.gov.br"
BULK_BASE_URL = "https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm"

CHAPTER_PHARMA = 30     # Medicamentos, vacinas, reagentes
CHAPTER_MEDDEVICE = 90  # Dispositivos médicos, equipamentos diagnóstico

MDIC_ENCODING = "latin-1"

DEFAULT_HEADERS = {
    "User-Agent": "PharmaIntelBR/1.0 (research; contact@pharmaintel.com.br)",
    "Accept": "application/json",
}

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class ComexStatError(Exception):
    """Base exception for Comex Stat errors."""


class ComexStatHTTPError(ComexStatError):
    """HTTP error from Comex Stat API."""


class ComexStatEmptyResponseError(ComexStatError):
    """API returned no data."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class ComexStatClient:
    """Client for the Comex Stat REST API."""

    def __init__(self, timeout: int = 60) -> None:
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.session.verify = False  # SSL workaround for Windows
        self.timeout = timeout

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            logger.warning("Rate limited. Waiting %ds...", retry_after)
            time.sleep(retry_after)
            raise requests.RequestException("Rate limited")
        if resp.status_code >= 400:
            raise ComexStatHTTPError(f"HTTP {resp.status_code}: {url}")
        return resp.json()

    def fetch_monthly_imports(
        self,
        year: int,
        chapter: int,
        month_start: int = 1,
        month_end: int = 12,
    ) -> pd.DataFrame:
        """
        Fetch monthly import data for a given NCM chapter.

        Returns DataFrame with columns:
          co_ano, co_mes, co_ncm, kg_liquido, vl_fob, vl_frete, vl_seguro
        """
        payload = {
            "flow": "import",
            "monthStart": f"{year}-{month_start:02d}",
            "monthEnd": f"{year}-{month_end:02d}",
            "filters": [{"filter": "chapter", "values": [str(chapter)]}],
            "details": ["chapter", "ncm"],
            "metrics": ["metricFOB", "metricKG"],
        }
        try:
            data = self._post("general/monthly", payload)
            records = data.get("data", {}).get("list", [])
            if not records:
                logger.warning("No data returned for chapter %d / %d", chapter, year)
                return pd.DataFrame()
            df = pd.DataFrame(records)
            return self._normalize_columns(df)
        except Exception as exc:
            logger.error("fetch_monthly_imports failed: %s", exc)
            return pd.DataFrame()

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        resp = self.session.post(url, json=payload, timeout=self.timeout)
        if resp.status_code >= 400:
            raise ComexStatHTTPError(f"HTTP {resp.status_code}: {url}")
        return resp.json()

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        rename = {
            "year": "co_ano",
            "month": "co_mes",
            "ncmCode": "co_ncm",
            "ncmDescription": "ds_ncm",
            "metricFOB": "vl_fob",
            "metricKG": "kg_liquido",
            "countryCode": "co_pais",
            "countryName": "ds_pais",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        for col in ["vl_fob", "kg_liquido"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df


# ---------------------------------------------------------------------------
# Bulk CSV download (fallback — arquivo anual do MDIC)
# ---------------------------------------------------------------------------
def download_bulk_csv(year: int, chapter: int, flow: str = "IMP") -> pd.DataFrame:
    """
    Download the annual bulk CSV from MDIC (fallback when API is unavailable).

    Args:
        year: 4-digit year (e.g. 2024)
        chapter: NCM chapter (30 or 90)
        flow: 'IMP' (import) or 'EXP' (export)

    Returns:
        DataFrame filtered to the given chapter.
    """
    filename = f"{flow}_{year}.csv"
    url = f"{BULK_BASE_URL}/{filename}"
    cache_path = RAW_DIR / filename

    if cache_path.exists():
        logger.info("Loading cached bulk CSV: %s", cache_path)
    else:
        logger.info("Downloading bulk CSV: %s", url)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, verify=False, timeout=120) as resp:
            resp.raise_for_status()
            with open(cache_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        logger.info("Saved: %s", cache_path)

    df = pd.read_csv(cache_path, sep=";", encoding=MDIC_ENCODING, dtype=str)
    df.columns = [c.lower() for c in df.columns]

    chapter_str = str(chapter).zfill(2)
    if "co_ncm" in df.columns:
        df = df[df["co_ncm"].str.startswith(chapter_str, na=False)]

    for col in ["vl_fob", "kg_liquido", "vl_frete", "vl_seguro", "co_ano", "co_mes"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------
def fetch_pharma_imports(year: int = 2024) -> pd.DataFrame:
    """
    Fetch Chapter 30 pharmaceutical imports for a given year.

    Tries the REST API first; falls back to bulk CSV download.
    """
    client = ComexStatClient()
    df = client.fetch_monthly_imports(year=year, chapter=CHAPTER_PHARMA)
    if df.empty:
        logger.info("API returned empty — falling back to bulk CSV.")
        df = download_bulk_csv(year=year, chapter=CHAPTER_PHARMA)
    return df
