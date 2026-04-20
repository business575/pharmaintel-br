"""
un_comtrade.py
==============
Integração com a API UN Comtrade Plus — dados de comércio internacional.

Fonte: https://comtradeplus.un.org
Documentação: https://comtradeplus.un.org/TradeFlow

Uso:
    - Comparar importações brasileiras com fluxos globais
    - Identificar fornecedores alternativos por produto (NCM/HS code)
    - Análise de preços FOB internacionais (benchmarking)

Nota: API key gratuita em https://comtradeplus.un.org
      SSL verify=False necessário em ambiente Windows.
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
# Constants
# ---------------------------------------------------------------------------
COMTRADE_BASE   = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
COMTRADE_BASE_V1 = "https://comtradeapi.un.org/data/v1/get"   # paid API key endpoint
COMTRADE_REF  = "https://comtradeapi.un.org/files/v1/app/reference"

# Brazil reporter code in UN Comtrade
BRAZIL_CODE = "76"

# Default HS chapters for pharma
HS_CHAPTER_PHARMA    = "30"
HS_CHAPTER_MEDDEVICE = "90"

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class ComtradeError(Exception):
    """Base UN Comtrade exception."""


class ComtradeHTTPError(ComtradeError):
    """HTTP error from Comtrade API."""


class ComtradeQuotaError(ComtradeError):
    """API quota exceeded."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class ComtradeClient:
    """
    Client for UN Comtrade Plus API (v1).

    Args:
        api_key: Comtrade API subscription key (required for data endpoints).
    """

    def __init__(self, api_key: str = "", timeout: int = 60) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = False  # SSL workaround for Windows
        self.session.headers.update({
            "User-Agent": "PharmaIntelBR/1.0",
            "Ocp-Apim-Subscription-Key": api_key,
        })

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=3, max=20),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _get(self, url: str, params: dict) -> dict:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 15))
            logger.warning("Comtrade rate limit. Waiting %ds...", wait)
            time.sleep(wait)
            raise requests.RequestException("Rate limited")
        if resp.status_code == 403:
            raise ComtradeQuotaError("API quota exceeded or invalid key")
        if resp.status_code >= 400:
            raise ComtradeHTTPError(f"HTTP {resp.status_code}: {url}")
        return resp.json()

    def fetch_brazil_imports(
        self,
        year: int = 2024,
        hs_chapter: str = HS_CHAPTER_PHARMA,
        partner_code: str = "0",  # 0 = World
    ) -> pd.DataFrame:
        """
        Fetch Brazil's pharmaceutical imports from UN Comtrade.

        Args:
            year: Reference year
            hs_chapter: 2-digit HS chapter (e.g. '30' for pharma)
            partner_code: Partner country code ('0' = all partners)

        Returns:
            DataFrame with trade flow data.
        """
        # UN Comtrade uses 6-digit HS codes; chapter = first 2 digits
        # We'll use the chapter-level aggregation
        params = {
            "reporterCode": BRAZIL_CODE,
            "period": str(year),
            "partnerCode": partner_code,
            "partner2Code": "0",
            "cmdCode": f"TOTAL",  # Will be overridden below
            "flowCode": "M",  # M = Import
            "typeCode": "C",  # C = Commodities
            "freqCode": "A",  # A = Annual
            "clCode": "HS",
            "includeDesc": True,
        }

        # Build HS commodity code filter (chapter level)
        params["cmdCode"] = f"{hs_chapter}"

        cache_key = f"comtrade_bra_{hs_chapter}_{year}.json"
        cache_path = RAW_DIR / cache_key

        if cache_path.exists():
            import json
            logger.info("Loading cached Comtrade data: %s", cache_key)
            with open(cache_path) as f:
                data = json.load(f)
        else:
            try:
                # Public endpoint — no API key required
                data = self._get(COMTRADE_BASE, params)
            except ComtradeHTTPError:
                # Fallback to paid endpoint if public fails
                if self.api_key:
                    try:
                        params["cmdCode"] = f"{hs_chapter}00-{hs_chapter}99"
                        data = self._get(COMTRADE_BASE_V1, params)
                    except Exception:
                        logger.warning("Comtrade paid endpoint failed — using demo data.")
                        return self._demo_data(year, hs_chapter)
                else:
                    logger.warning("Comtrade public endpoint failed — using demo data.")
                    return self._demo_data(year, hs_chapter)
            except ComtradeQuotaError:
                logger.warning("Comtrade quota exceeded — using demo data.")
                return self._demo_data(year, hs_chapter)

            RAW_DIR.mkdir(parents=True, exist_ok=True)
            import json
            with open(cache_path, "w") as f:
                json.dump(data, f)

        records = data.get("data", [])
        if not records:
            logger.warning("Comtrade returned no data — using demo data.")
            return self._demo_data(year, hs_chapter)

        df = pd.DataFrame(records)
        return self._normalize(df)

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        rename = {
            "refYear": "ano",
            "reporterCode": "reporter_code",
            "reporterDesc": "reporter",
            "partnerCode": "partner_code",
            "partnerDesc": "partner",
            "cmdCode": "hs_code",
            "cmdDesc": "ds_produto",
            "flowCode": "flow",
            "primaryValue": "vl_usd",
            "netWgt": "kg_liquido",
            "qty": "qty",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        for col in ["vl_usd", "kg_liquido"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df

    def _demo_data(self, year: int, hs_chapter: str) -> pd.DataFrame:
        """Return realistic demo data when API is unavailable."""
        import numpy as np
        rng = np.random.default_rng(seed=int(hs_chapter) + year)

        partners = [
            ("276", "Germany"), ("840", "United States"), ("356", "India"),
            ("156", "China"), ("380", "Italy"), ("756", "Switzerland"),
            ("528", "Netherlands"), ("250", "France"), ("724", "Spain"),
            ("826", "United Kingdom"),
        ]
        rows = []
        for code, name in partners:
            base_val = rng.integers(10_000_000, 800_000_000)
            rows.append({
                "ano": year,
                "partner_code": code,
                "partner": name,
                "hs_code": f"{hs_chapter}00",
                "ds_produto": f"Chapter {hs_chapter} products",
                "flow": "M",
                "vl_usd": float(base_val),
                "kg_liquido": float(base_val / rng.uniform(15, 80)),
                "_demo": True,
            })
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------
def fetch_brazil_pharma_imports_comtrade(
    year: int = 2024,
    api_key: str = "",
) -> pd.DataFrame:
    """Fetch Brazil Chapter 30 imports from UN Comtrade."""
    client = ComtradeClient(api_key=api_key)
    return client.fetch_brazil_imports(year=year, hs_chapter=HS_CHAPTER_PHARMA)
