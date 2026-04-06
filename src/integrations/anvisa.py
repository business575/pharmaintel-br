"""
anvisa.py
=========
Integração com dados abertos da ANVISA — medicamentos registrados.

Fonte: https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv
Sem autenticação necessária — dados abertos.

Nota: SSL verify=False necessário em ambiente Windows.
"""

from __future__ import annotations

import io
import logging
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
OPEN_DATA_URL = "https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv"
PRODUTOS_SAUDE_URL = "https://dados.anvisa.gov.br/dados/CONSULTAS/PRODUTOS/TA_CONSULTA_PRODUTOS_SAUDE.CSV"

ANVISA_ENCODING = "latin-1"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

SITUACAO_ATIVA = {"VÁLIDO", "ATIVO", "VÁLIDO - PUBLICADO"}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class AnvisaError(Exception):
    """Base ANVISA exception."""


class AnvisaHTTPError(AnvisaError):
    """HTTP error fetching ANVISA data."""


class AnvisaEmptyError(AnvisaError):
    """No data returned."""


class AnvisaAuthError(AnvisaError):
    """Authentication error."""


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------
@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=3, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _download_csv(url: str, cache_path: Path, encoding: str = ANVISA_ENCODING) -> pd.DataFrame:
    """Download a CSV file with caching."""
    if cache_path.exists():
        logger.info("Loading cached ANVISA data: %s", cache_path.name)
        return pd.read_csv(cache_path, sep=";", encoding=encoding, dtype=str, low_memory=False)

    logger.info("Downloading ANVISA open data: %s", url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(url, verify=False, timeout=120, stream=True)
    if resp.status_code >= 400:
        raise AnvisaHTTPError(f"HTTP {resp.status_code}: {url}")

    content = b""
    for chunk in resp.iter_content(chunk_size=1 << 20):
        content += chunk

    cache_path.write_bytes(content)
    logger.info("Saved: %s (%.1f MB)", cache_path.name, len(content) / 1e6)

    return pd.read_csv(
        io.BytesIO(content),
        sep=";",
        encoding=encoding,
        dtype=str,
        low_memory=False,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_medicamentos_registrados(use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch all registered medications from ANVISA open data.

    Returns DataFrame with normalized columns:
        numero_registro, nome_produto, empresa, situacao, vencimento,
        classe_terapeutica, principio_ativo, pais_origem
    """
    cache_path = RAW_DIR / "anvisa_medicamentos.csv"
    if not use_cache and cache_path.exists():
        cache_path.unlink()

    try:
        df = _download_csv(OPEN_DATA_URL, cache_path)
    except Exception as exc:
        logger.error("Failed to fetch ANVISA medications: %s", exc)
        return pd.DataFrame()

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    rename = {
        "numero_registro_produto": "numero_registro",
        "nome_produto": "nome_produto",
        "empresa_detentora_registro": "empresa",
        "situacao_registro": "situacao",
        "data_vencimento_registro": "vencimento",
        "classe_terapeutica": "classe_terapeutica",
        "principio_ativo": "principio_ativo",
        "pais_origem": "pais_origem",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "situacao" in df.columns:
        df["ativo"] = df["situacao"].str.upper().str.strip().isin(SITUACAO_ATIVA)

    if "vencimento" in df.columns:
        df["vencimento"] = pd.to_datetime(df["vencimento"], dayfirst=True, errors="coerce")

    return df.reset_index(drop=True)


def fetch_produtos_saude_registrados(use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch registered health products (medical devices) from ANVISA.
    Covers NCM Chapter 90.
    """
    cache_path = RAW_DIR / "anvisa_produtos_saude.csv"
    if not use_cache and cache_path.exists():
        cache_path.unlink()

    try:
        df = _download_csv(PRODUTOS_SAUDE_URL, cache_path)
    except Exception as exc:
        logger.error("Failed to fetch ANVISA health products: %s", exc)
        return pd.DataFrame()

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df.reset_index(drop=True)


def get_active_registrations(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Return only active/valid registrations from a medications DataFrame."""
    if df is None:
        df = fetch_medicamentos_registrados()
    if df.empty or "ativo" not in df.columns:
        return df
    return df[df["ativo"]].copy()
