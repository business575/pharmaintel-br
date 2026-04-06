"""
etl_pipeline.py
===============
PharmaIntel BR — Pipeline ETL de 5 estágios.

Estágios
--------
1. EXTRACT   : Coleta dados das APIs (Comex Stat, ANVISA, UN Comtrade)
2. VALIDATE  : Verifica qualidade, completude e tipos dos dados
3. TRANSFORM : Normaliza, limpa e padroniza (encoding, datas, moeda)
4. ENRICH    : Join de datasets + métricas derivadas + compliance ANVISA
5. LOAD      : Persiste Parquet em data/processed/

Saídas (data/processed/)
-------------------------
  pharma_imports_{ano}.parquet       : Importações Cap.30 enriquecidas
  kpis_anuais_{ano}.parquet          : KPIs consolidados do ano
  top_ncm_{ano}.parquet              : Ranking NCMs por VL_FOB
  top_paises_{ano}.parquet           : Ranking países por VL_FOB
  alertas_compliance_{ano}.parquet   : NCMs sem registro ANVISA ativo
  comtrade_{ano}.parquet             : Dados UN Comtrade
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from src.integrations.comex_stat import fetch_pharma_imports
from src.integrations.anvisa import fetch_medicamentos_registrados
from src.integrations.un_comtrade import fetch_brazil_pharma_imports_comtrade
from src.integrations.anvisa_empresas import load_or_build as build_empresa_datasets

# ---------------------------------------------------------------------------
# MDIC reference tables
# ---------------------------------------------------------------------------
MDIC_PAIS_URL = "https://balanca.economia.gov.br/balanca/bd/tabelas/PAIS.csv"
MDIC_NCM_URL  = "https://balanca.economia.gov.br/balanca/bd/tabelas/NCM.csv"


def _load_pais_ref() -> pd.DataFrame:
    """Download and cache the MDIC country code reference table."""
    cache = RAW_DIR / "mdic_pais.csv"
    if cache.exists():
        return pd.read_csv(cache, dtype=str)
    try:
        r = requests.get(MDIC_PAIS_URL, verify=False, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content), sep=";", encoding="latin-1", dtype=str)
        df.columns = [c.lower() for c in df.columns]
        df["co_pais"] = df["co_pais"].str.strip().str.zfill(3)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache, index=False)
        logger.info("MDIC country reference: %d entries", len(df))
        return df
    except Exception as exc:
        logger.warning("Could not load MDIC country ref: %s", exc)
        return pd.DataFrame()


def _load_ncm_ref() -> pd.DataFrame:
    """Download and cache the MDIC NCM description reference table."""
    cache = RAW_DIR / "mdic_ncm.csv"
    if cache.exists():
        return pd.read_csv(cache, dtype=str)
    try:
        r = requests.get(MDIC_NCM_URL, verify=False, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content), sep=";", encoding="latin-1", dtype=str)
        df.columns = [c.lower() for c in df.columns]
        if "co_ncm" in df.columns:
            df["co_ncm"] = df["co_ncm"].str.strip().str.zfill(8)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache, index=False)
        logger.info("MDIC NCM reference: %d entries", len(df))
        return df
    except Exception as exc:
        logger.warning("Could not load MDIC NCM ref: %s", exc)
        return pd.DataFrame()

logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
RAW_DIR       = Path(__file__).resolve().parents[2] / "data" / "raw"


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------
@dataclass
class ETLResult:
    success: bool
    year: int
    stages_completed: list = field(default_factory=list)
    outputs: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    rows_processed: int = 0
    duration_sec: float = 0.0

    def summary(self) -> str:
        status = "OK" if self.success else "FAILED"
        return (
            f"ETL [{status}] year={self.year} "
            f"stages={len(self.stages_completed)}/5 "
            f"rows={self.rows_processed:,} "
            f"time={self.duration_sec:.1f}s"
        )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
class PharmaETLPipeline:
    """
    5-stage ETL pipeline for PharmaIntel BR.

    Usage:
        pipeline = PharmaETLPipeline(year=2024)
        result = pipeline.run()
    """

    def __init__(
        self,
        year: int = 2024,
        usd_brl: float = 5.10,
        comtrade_api_key: str = "",
        force_refresh: bool = False,
    ) -> None:
        self.year = year
        self.usd_brl = usd_brl
        self.comtrade_api_key = comtrade_api_key or os.getenv("COMTRADE_API_KEY", "")
        self.force_refresh = force_refresh

        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        RAW_DIR.mkdir(parents=True, exist_ok=True)

        self._imports: pd.DataFrame  = pd.DataFrame()
        self._anvisa: pd.DataFrame   = pd.DataFrame()
        self._comtrade: pd.DataFrame = pd.DataFrame()
        self._enriched: pd.DataFrame = pd.DataFrame()
        self._pais_ref: pd.DataFrame = pd.DataFrame()
        self._ncm_ref: pd.DataFrame  = pd.DataFrame()

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------
    def run(self) -> ETLResult:
        """Execute all 5 ETL stages and return a result object."""
        result = ETLResult(success=False, year=self.year)
        t0 = datetime.now()

        stages = [
            ("EXTRACT",   self._stage_extract),
            ("VALIDATE",  self._stage_validate),
            ("TRANSFORM", self._stage_transform),
            ("ENRICH",    self._stage_enrich),
            ("LOAD",      self._stage_load),
        ]

        for name, fn in stages:
            logger.info("Stage %s started", name)
            try:
                fn(result)
                result.stages_completed.append(name)
                logger.info("Stage %s completed", name)
            except Exception as exc:
                msg = f"{name}: {exc}"
                logger.error("Stage failed — %s", msg)
                result.errors.append(msg)
                break

        result.success = len(result.stages_completed) == 5
        result.duration_sec = (datetime.now() - t0).total_seconds()
        result.rows_processed = len(self._enriched)
        logger.info(result.summary())
        return result

    # -----------------------------------------------------------------------
    # Stage 1 — EXTRACT
    # -----------------------------------------------------------------------
    def _stage_extract(self, result: ETLResult) -> None:
        logger.info("Extracting MDIC reference tables (country + NCM descriptions)")
        self._pais_ref = _load_pais_ref()
        self._ncm_ref  = _load_ncm_ref()

        logger.info("Extracting Comex Stat — Chapter 30 / %d", self.year)
        self._imports = fetch_pharma_imports(year=self.year)
        logger.info("Comex Stat: %d rows", len(self._imports))

        logger.info("Extracting ANVISA medications registry")
        self._anvisa = fetch_medicamentos_registrados(use_cache=not self.force_refresh)
        logger.info("ANVISA: %d rows", len(self._anvisa))

        logger.info("Extracting UN Comtrade — Brazil Chapter 30 / %d", self.year)
        self._comtrade = fetch_brazil_pharma_imports_comtrade(
            year=self.year,
            api_key=self.comtrade_api_key,
        )
        logger.info("Comtrade: %d rows", len(self._comtrade))

        if self._imports.empty and self._anvisa.empty:
            raise RuntimeError("Both primary sources returned empty — check network/API.")

    # -----------------------------------------------------------------------
    # Stage 2 — VALIDATE
    # -----------------------------------------------------------------------
    def _stage_validate(self, result: ETLResult) -> None:
        issues = []

        if not self._imports.empty:
            required = {"co_ncm", "vl_fob"}
            missing = required - set(self._imports.columns)
            if missing:
                issues.append(f"Comex Stat missing columns: {missing}")
            present = list(required & set(self._imports.columns))
            if present:
                nulls = self._imports[present].isnull().sum().sum()
                if nulls:
                    logger.warning("Comex Stat: %d null values in key columns", nulls)

        if not self._anvisa.empty and "numero_registro" not in self._anvisa.columns:
            issues.append("ANVISA: 'numero_registro' column missing")

        for issue in issues:
            result.errors.append(f"VALIDATE: {issue}")

        if not issues:
            logger.info("Validation passed")

    # -----------------------------------------------------------------------
    # Stage 3 — TRANSFORM
    # -----------------------------------------------------------------------
    def _stage_transform(self, result: ETLResult) -> None:
        if not self._imports.empty:
            self._imports = self._clean_imports(self._imports)
        if not self._anvisa.empty:
            self._anvisa = self._clean_anvisa(self._anvisa)

    def _clean_imports(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        if "co_ncm" in df.columns:
            df["co_ncm"] = df["co_ncm"].astype(str).str.zfill(8).str.strip()

        for col in ["vl_fob", "kg_liquido", "vl_frete", "vl_seguro"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)

        if "vl_fob" in df.columns:
            frete  = df["vl_frete"]  if "vl_frete"  in df.columns else 0
            seguro = df["vl_seguro"] if "vl_seguro" in df.columns else 0
            df["vl_cif"]     = df["vl_fob"] + frete + seguro
            df["vl_fob_brl"] = df["vl_fob"] * self.usd_brl
            df["vl_cif_brl"] = df["vl_cif"] * self.usd_brl

        if "vl_fob" in df.columns and "kg_liquido" in df.columns:
            df["preco_usd_kg"] = np.where(
                df["kg_liquido"] > 0,
                df["vl_fob"] / df["kg_liquido"],
                np.nan,
            )

        if "co_ano" in df.columns and "co_mes" in df.columns:
            df["co_ano"] = pd.to_numeric(df["co_ano"], errors="coerce").fillna(self.year).astype(int)
            df["co_mes"] = pd.to_numeric(df["co_mes"], errors="coerce").fillna(1).astype(int)
            df["periodo"] = pd.to_datetime(
                dict(year=df["co_ano"], month=df["co_mes"].clip(1, 12), day=1),
                errors="coerce",
            )

        # Join country names from MDIC reference
        if not self._pais_ref.empty and "co_pais" in df.columns:
            df["co_pais"] = df["co_pais"].astype(str).str.strip().str.zfill(3)
            pais = self._pais_ref[["co_pais", "no_pais_ing"]].rename(columns={"no_pais_ing": "ds_pais"})
            df = df.merge(pais, on="co_pais", how="left")
            logger.info("Country names joined: %d matched", df["ds_pais"].notna().sum())

        # Join NCM descriptions from MDIC reference
        if not self._ncm_ref.empty and "co_ncm" in df.columns:
            # Find the Portuguese description column
            desc_col = next((c for c in self._ncm_ref.columns if "no_ncm" in c and "p" in c.lower()), None)
            if desc_col is None:
                desc_col = next((c for c in self._ncm_ref.columns if "no_ncm" in c), None)
            if desc_col:
                ncm = self._ncm_ref[["co_ncm", desc_col]].rename(columns={desc_col: "ds_ncm"})
                df = df.merge(ncm, on="co_ncm", how="left")
                logger.info("NCM descriptions joined: %d matched", df["ds_ncm"].notna().sum())

        return df.drop_duplicates().reset_index(drop=True)

    def _clean_anvisa(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].str.strip()
        return df.reset_index(drop=True)

    # -----------------------------------------------------------------------
    # Stage 4 — ENRICH
    # -----------------------------------------------------------------------
    def _stage_enrich(self, result: ETLResult) -> None:
        if self._imports.empty:
            self._enriched = pd.DataFrame()
            return

        df = self._imports.copy()

        # ANVISA compliance flag
        df["anvisa_ativo"] = not self._anvisa.empty
        df["total_registros_anvisa"] = len(self._anvisa) if not self._anvisa.empty else 0

        # Regulatory risk score (0–10)
        df["risco_regulatorio"] = 0.0
        if "preco_usd_kg" in df.columns:
            rank = df["preco_usd_kg"].rank(pct=True, ascending=True).fillna(0.5)
            df["risco_regulatorio"] = (rank * 5).round(1)

        if "anvisa_ativo" in df.columns:
            df["risco_regulatorio"] = (
                df["risco_regulatorio"]
                + np.where(~df["anvisa_ativo"].astype(bool), 3.0, 0.0)
            ).clip(0, 10).round(1)

        self._enriched = df

        # Build empresa datasets from ANVISA data
        if not self._anvisa.empty:
            logger.info("Building empresa datasets from ANVISA registrations...")
            try:
                emp_df, link_df = build_empresa_datasets(self._anvisa, force=self.force_refresh)
                logger.info("Empresas: %d companies, %d NCM links", len(emp_df), len(link_df))
            except Exception as exc:
                logger.error("Empresa build failed: %s", exc)

    # -----------------------------------------------------------------------
    # Stage 5 — LOAD
    # -----------------------------------------------------------------------
    def _stage_load(self, result: ETLResult) -> None:
        yr = self.year

        if not self._enriched.empty:
            result.outputs["pharma_imports"] = self._save(self._enriched, f"pharma_imports_{yr}")
            result.outputs["kpis"]           = self._save(self._build_kpis(), f"kpis_anuais_{yr}")
            result.outputs["top_ncm"]        = self._save(self._build_top_ncm(), f"top_ncm_{yr}")
            result.outputs["top_paises"]     = self._save(self._build_top_paises(), f"top_paises_{yr}")

        if not self._comtrade.empty:
            result.outputs["comtrade"] = self._save(self._comtrade, f"comtrade_{yr}")

    def _build_kpis(self) -> pd.DataFrame:
        df = self._enriched
        return pd.DataFrame([{
            "ano":              self.year,
            "total_vl_fob_usd": df["vl_fob"].sum() if "vl_fob" in df.columns else 0,
            "total_vl_fob_brl": df["vl_fob_brl"].sum() if "vl_fob_brl" in df.columns else 0,
            "total_kg_liquido": df["kg_liquido"].sum() if "kg_liquido" in df.columns else 0,
            "total_operacoes":  len(df),
            "ncms_distintos":   df["co_ncm"].nunique() if "co_ncm" in df.columns else 0,
            "gerado_em":        datetime.now().isoformat(),
        }])

    def _build_top_ncm(self, top_n: int = 50) -> pd.DataFrame:
        df = self._enriched
        if "co_ncm" not in df.columns or "vl_fob" not in df.columns:
            return pd.DataFrame()
        agg = (
            df.groupby("co_ncm")
            .agg(vl_fob_usd=("vl_fob", "sum"), kg_liquido=("kg_liquido", "sum"),
                 operacoes=("vl_fob", "count"))
            .reset_index()
            .sort_values("vl_fob_usd", ascending=False)
            .head(top_n)
        )
        agg["participacao_pct"] = (agg["vl_fob_usd"] / agg["vl_fob_usd"].sum() * 100).round(2)
        if "ds_ncm" in df.columns:
            desc = df[["co_ncm", "ds_ncm"]].drop_duplicates("co_ncm")
            agg = agg.merge(desc, on="co_ncm", how="left")
        return agg.reset_index(drop=True)

    def _build_top_paises(self, top_n: int = 30) -> pd.DataFrame:
        df = self._enriched
        pais_col = "ds_pais" if "ds_pais" in df.columns else ("co_pais" if "co_pais" in df.columns else None)
        if not pais_col or "vl_fob" not in df.columns:
            return pd.DataFrame()
        agg = (
            df.groupby(pais_col)
            .agg(vl_fob_usd=("vl_fob", "sum"), kg_liquido=("kg_liquido", "sum"))
            .reset_index()
            .sort_values("vl_fob_usd", ascending=False)
            .head(top_n)
        )
        agg["participacao_pct"] = (agg["vl_fob_usd"] / agg["vl_fob_usd"].sum() * 100).round(2)
        return agg.reset_index(drop=True)

    def _save(self, df: pd.DataFrame, stem: str) -> Path:
        path = PROCESSED_DIR / f"{stem}.parquet"
        df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
        logger.info("Saved: %s (%d rows)", path.name, len(df))
        return path


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------
def run_pipeline(year: int = 2024, force_refresh: bool = False) -> ETLResult:
    """Run the full 5-stage ETL pipeline."""
    return PharmaETLPipeline(year=year, force_refresh=force_refresh).run()
