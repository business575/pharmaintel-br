"""
bps.py
======
Integração com o Banco de Preços em Saúde (BPS) — Ministério da Saúde.

Fonte: https://bps.saude.gov.br
API pública, sem autenticação.

Permite consultar preços pagos pelo governo em compras públicas de:
- Medicamentos (incluindo soros, insulinas, oncológicos)
- Dispositivos médicos
- Materiais hospitalares

Por produto (código CATMAT/ANVISA), estado, período e fabricante.
"""

from __future__ import annotations

import logging
import urllib3
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
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
BPS_BASE_URL  = "https://bps.saude.gov.br/bps/api/public"
BPS_SEARCH    = f"{BPS_BASE_URL}/compra/search"
BPS_PRODUTO   = f"{BPS_BASE_URL}/produto/search"

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TIMEOUT = 20
MAX_RESULTS     = 500


class BPSError(Exception):
    pass


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------
_retry = retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Core search
# ---------------------------------------------------------------------------

@_retry
def search_precos(
    descricao: str,
    uf: Optional[str] = None,
    ano: Optional[int] = None,
    limit: int = 100,
) -> pd.DataFrame:
    """
    Search BPS for government purchase prices of a product.

    Args:
        descricao: Product name or description (e.g. "soro fisiologico 500ml")
        uf:        State code (e.g. "RJ", "SP") — optional
        ano:       Year filter (e.g. 2025) — optional
        limit:     Max rows to return

    Returns:
        DataFrame with columns: descricao, fabricante, uf, quantidade,
        valor_unitario, valor_total, data_compra, modalidade, orgao
    """
    params: dict = {
        "descricao": descricao,
        "page":      0,
        "size":      min(limit, MAX_RESULTS),
    }
    if uf:
        params["uf"] = uf.upper()
    if ano:
        params["ano"] = ano

    try:
        resp = requests.get(
            BPS_SEARCH,
            params=params,
            timeout=DEFAULT_TIMEOUT,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as exc:
        raise BPSError(f"BPS HTTP error: {exc}") from exc
    except Exception as exc:
        raise BPSError(f"BPS request failed: {exc}") from exc

    # BPS returns paginated JSON — extract content list
    content = data if isinstance(data, list) else data.get("content", data.get("data", []))
    if not content:
        return pd.DataFrame()

    df = pd.json_normalize(content)
    df = _normalize_columns(df)
    return df.head(limit)


@_retry
def search_produto(descricao: str, limit: int = 50) -> pd.DataFrame:
    """
    Search BPS product catalogue by description.
    Returns product codes, descriptions and categories.
    """
    params = {"descricao": descricao, "page": 0, "size": min(limit, 100)}
    try:
        resp = requests.get(
            BPS_PRODUTO,
            params=params,
            timeout=DEFAULT_TIMEOUT,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        raise BPSError(f"BPS produto search failed: {exc}") from exc

    content = data if isinstance(data, list) else data.get("content", [])
    if not content:
        return pd.DataFrame()
    return pd.json_normalize(content).head(limit)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_COLUMN_MAP = {
    # Portuguese field names from BPS API
    "dsItem":           "descricao",
    "nmFabricante":     "fabricante",
    "sgUf":             "uf",
    "qtItem":           "quantidade",
    "vlUnitarioItem":   "valor_unitario",
    "vlTotalItem":      "valor_total",
    "dtCompra":         "data_compra",
    "nmModalidade":     "modalidade",
    "nmOrgao":          "orgao",
    "nmMunicipio":      "municipio",
    "anoCompra":        "ano",
    "coItem":           "codigo_catmat",
    # Alternative field names
    "descricaoItem":    "descricao",
    "fabricante":       "fabricante",
    "uf":               "uf",
    "quantidade":       "quantidade",
    "valorUnitario":    "valor_unitario",
    "valorTotal":       "valor_total",
    "dataCompra":       "data_compra",
    "modalidade":       "modalidade",
    "orgao":            "orgao",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={k: v for k, v in _COLUMN_MAP.items() if k in df.columns})

    # Ensure numeric
    for col in ["valor_unitario", "valor_total", "quantidade"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse dates
    if "data_compra" in df.columns:
        df["data_compra"] = pd.to_datetime(df["data_compra"], errors="coerce")

    # Keep only known columns that exist
    keep = [c for c in _COLUMN_MAP.values() if c in df.columns]
    extra = [c for c in df.columns if c not in keep]
    return df[keep + extra[:3]]  # keep up to 3 extra unknown cols


# ---------------------------------------------------------------------------
# Convenience summary
# ---------------------------------------------------------------------------

def get_price_summary(
    descricao: str,
    uf: Optional[str] = None,
    ano: Optional[int] = None,
) -> dict:
    """
    Return a price summary dict for use in the AI agent tool.

    Returns:
        {
          "produto": str,
          "uf": str | None,
          "ano": int | None,
          "total_compras": int,
          "preco_minimo": float,
          "preco_maximo": float,
          "preco_medio": float,
          "preco_mediano": float,
          "top_fabricantes": list[str],
          "top_orgaos": list[str],
          "sample": list[dict],   # up to 5 rows
        }
    """
    try:
        df = search_precos(descricao, uf=uf, ano=ano, limit=200)
    except BPSError as exc:
        return {"error": str(exc)}

    if df.empty:
        return {
            "produto": descricao,
            "uf": uf,
            "ano": ano,
            "total_compras": 0,
            "mensagem": "Nenhuma compra encontrada para os filtros informados.",
        }

    vu = df["valor_unitario"].dropna() if "valor_unitario" in df.columns else pd.Series(dtype=float)

    top_fab = (
        df["fabricante"].value_counts().head(5).index.tolist()
        if "fabricante" in df.columns else []
    )
    top_org = (
        df["orgao"].value_counts().head(5).index.tolist()
        if "orgao" in df.columns else []
    )

    sample_cols = ["descricao", "fabricante", "uf", "valor_unitario", "quantidade", "data_compra", "orgao"]
    sample_cols = [c for c in sample_cols if c in df.columns]
    sample = df[sample_cols].head(5).to_dict(orient="records")

    return {
        "produto":        descricao,
        "uf":             uf,
        "ano":            ano,
        "total_compras":  len(df),
        "preco_minimo":   round(float(vu.min()), 4) if len(vu) else None,
        "preco_maximo":   round(float(vu.max()), 4) if len(vu) else None,
        "preco_medio":    round(float(vu.mean()), 4) if len(vu) else None,
        "preco_mediano":  round(float(vu.median()), 4) if len(vu) else None,
        "top_fabricantes": top_fab,
        "top_orgaos":      top_org,
        "sample":          sample,
    }
