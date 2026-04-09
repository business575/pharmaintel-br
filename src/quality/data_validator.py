"""
data_validator.py — PharmaIntel BR Data Quality Validator

Validates pharma import data (Comex Stat) and ANVISA registrations
before they reach clients. Target: 99% accuracy, 0% critical errors.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

NCM_PHARMA_CHAPTERS = {"30", "90"}
FOB_MAX_PLAUSIBLE_USD = 150_000_000
FOB_ZERO_WARN_PCT = 0.05  # warn if > 5% of rows have zero FOB


@dataclass
class ValidationResult:
    passed: bool
    score: int                          # 0-100; 100 = perfect
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    @property
    def result_str(self) -> str:
        if not self.passed:
            return "fail"
        if self.warnings:
            return "warn"
        return "pass"

    @property
    def error_level(self) -> str:
        if not self.passed and self.score < 40:
            return "critical"
        if not self.passed or self.score < 70:
            return "medium"
        return "low"

    def to_details_json(self) -> str:
        return json.dumps(
            {"score": self.score, "errors": self.errors,
             "warnings": self.warnings, **self.details},
            ensure_ascii=False, default=str,
        )


class PharmaDataValidator:
    """Validates pharmaceutical import and ANVISA data."""

    # ------------------------------------------------------------------
    # NCM
    # ------------------------------------------------------------------

    def validate_ncm_series(self, series: pd.Series) -> ValidationResult:
        """Validate a Series of NCM codes (must be 8-digit, chapters 30 or 90)."""
        errors, warnings = [], []
        details: dict = {}
        score = 100

        s = series.dropna().astype(str)
        invalid_fmt = s[~s.str.match(r"^\d{8}$")]
        wrong_chap  = s[s.str.match(r"^\d{8}$") & ~s.str[:2].isin(NCM_PHARMA_CHAPTERS)]

        if len(invalid_fmt) > 0:
            errors.append(f"NCM formato inválido: {len(invalid_fmt)} registros")
            details["invalid_format_count"] = int(len(invalid_fmt))
            details["invalid_format_sample"] = invalid_fmt.head(3).tolist()
            score -= 30

        if len(wrong_chap) > 0:
            warnings.append(f"NCM fora dos capítulos 30/90: {len(wrong_chap)} registros")
            details["wrong_chapter_count"] = int(len(wrong_chap))
            details["wrong_chapter_sample"] = wrong_chap.head(3).tolist()
            score -= 15

        score = max(0, score)
        return ValidationResult(
            passed=len(errors) == 0, score=score,
            errors=errors, warnings=warnings, details=details,
        )

    def validate_ncm_code(self, ncm: str) -> ValidationResult:
        """Single NCM code validation."""
        ncm = str(ncm).strip()
        if not re.match(r"^\d{8}$", ncm):
            return ValidationResult(False, 0, errors=[f"NCM inválido: {ncm}"])
        if ncm[:2] not in NCM_PHARMA_CHAPTERS:
            return ValidationResult(True, 70, warnings=[f"NCM capítulo {ncm[:2]} — fora do escopo farmacêutico"])
        return ValidationResult(True, 100)

    # ------------------------------------------------------------------
    # FOB values
    # ------------------------------------------------------------------

    def validate_fob_series(self, series: pd.Series) -> ValidationResult:
        """Validate FOB USD values — no negatives, plausible range."""
        errors, warnings = [], []
        details: dict = {}
        score = 100

        s = pd.to_numeric(series, errors="coerce")
        negatives = s[s < 0]
        zeros     = s[s == 0]
        outliers  = s[s > FOB_MAX_PLAUSIBLE_USD]

        if len(negatives) > 0:
            errors.append(f"FOB negativo: {len(negatives)} registros")
            details["negative_fob_count"] = int(len(negatives))
            score -= 40

        if len(zeros) / max(len(s), 1) > FOB_ZERO_WARN_PCT:
            warnings.append(f"FOB zero: {len(zeros)} registros ({len(zeros)/len(s)*100:.1f}%)")
            details["zero_fob_count"] = int(len(zeros))
            score -= 10

        if len(outliers) > 0:
            warnings.append(f"FOB acima de US$150M: {len(outliers)} registros (verificar)")
            details["outlier_fob_count"] = int(len(outliers))
            score -= 10

        score = max(0, score)
        return ValidationResult(
            passed=len(errors) == 0, score=score,
            errors=errors, warnings=warnings, details=details,
        )

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------

    def validate_dates_series(
        self, series: pd.Series, reference_date: Optional[datetime] = None
    ) -> ValidationResult:
        """Validate date column — no future dates, not too old."""
        errors, warnings = [], []
        details: dict = {}
        score = 100
        ref = reference_date or datetime.now(timezone.utc)

        s = pd.to_datetime(series, errors="coerce")
        nulls   = s[s.isna()]
        future  = s[s > ref]
        too_old = s[s < pd.Timestamp("2010-01-01")]

        if len(nulls) > 0:
            warnings.append(f"Datas nulas: {len(nulls)} registros")
            details["null_date_count"] = int(len(nulls))
            score -= 5

        if len(future) > 0:
            errors.append(f"Datas futuras inválidas: {len(future)} registros")
            details["future_date_count"] = int(len(future))
            score -= 30

        if len(too_old) > 0:
            warnings.append(f"Datas anteriores a 2010: {len(too_old)} registros")
            details["too_old_count"] = int(len(too_old))
            score -= 10

        score = max(0, score)
        return ValidationResult(
            passed=len(errors) == 0, score=score,
            errors=errors, warnings=warnings, details=details,
        )

    # ------------------------------------------------------------------
    # Country codes (MDIC 3-digit format)
    # ------------------------------------------------------------------

    def validate_country_codes(self, series: pd.Series) -> ValidationResult:
        """Validate MDIC 3-digit country codes."""
        errors, warnings = [], []
        details: dict = {}
        score = 100

        s = series.dropna().astype(str)
        invalid = s[~s.str.match(r"^\d{3}$")]

        if len(invalid) > 0:
            errors.append(f"Código de país inválido: {len(invalid)} registros")
            details["invalid_country_count"] = int(len(invalid))
            details["invalid_sample"] = invalid.head(3).tolist()
            score -= 20

        # Optional: referential check against MDIC file
        mdic_codes = self._load_mdic_country_codes()
        if mdic_codes:
            valid_fmt = s[s.str.match(r"^\d{3}$")]
            unknown = valid_fmt[~valid_fmt.isin(mdic_codes)]
            if len(unknown) > 0:
                warnings.append(f"Códigos MDIC não reconhecidos: {len(unknown)} registros")
                details["unknown_country_count"] = int(len(unknown))
                score -= 5

        score = max(0, score)
        return ValidationResult(
            passed=len(errors) == 0, score=score,
            errors=errors, warnings=warnings, details=details,
        )

    def _load_mdic_country_codes(self) -> set:
        cache_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "mdic_pais.csv"
        if cache_path.exists():
            try:
                df = pd.read_csv(cache_path, dtype=str)
                col = "co_pais" if "co_pais" in df.columns else df.columns[0]
                return set(df[col].str.strip().str.zfill(3).dropna())
            except Exception:
                pass
        return set()

    # ------------------------------------------------------------------
    # Duplicates
    # ------------------------------------------------------------------

    def validate_duplicates(
        self, df: pd.DataFrame, key_cols: list
    ) -> ValidationResult:
        """Detect exact duplicate rows across key columns."""
        errors, warnings = [], []
        details: dict = {}
        score = 100

        existing_cols = [c for c in key_cols if c in df.columns]
        if not existing_cols:
            return ValidationResult(True, 100, warnings=["Colunas chave não encontradas — skip duplicatas"])

        dupes = df[df.duplicated(subset=existing_cols, keep=False)]
        if len(dupes) > 0:
            errors.append(f"Linhas duplicadas: {len(dupes)} registros")
            details["duplicate_count"] = int(len(dupes))
            score -= 25

        score = max(0, score)
        return ValidationResult(
            passed=len(errors) == 0, score=score,
            errors=errors, warnings=warnings, details=details,
        )

    # ------------------------------------------------------------------
    # Data freshness
    # ------------------------------------------------------------------

    def validate_freshness(
        self, last_data_date: datetime, expected_lag_days: int = 45
    ) -> ValidationResult:
        """Check if data is current enough (Comex Stat lags ~30-45 days)."""
        now = datetime.now(timezone.utc)
        if last_data_date.tzinfo is None:
            last_data_date = last_data_date.replace(tzinfo=timezone.utc)

        lag_days = (now - last_data_date).days
        details = {"lag_days": lag_days, "expected_lag_days": expected_lag_days}

        if lag_days > 90:
            return ValidationResult(
                False, 30,
                errors=[f"Dados com {lag_days} dias de defasagem (crítico: >90 dias)"],
                details=details,
            )
        if lag_days > expected_lag_days:
            return ValidationResult(
                True, 70,
                warnings=[f"Dados com {lag_days} dias de defasagem (esperado: ≤{expected_lag_days} dias)"],
                details=details,
            )
        return ValidationResult(True, 100, details=details)

    # ------------------------------------------------------------------
    # ANVISA registration numbers
    # ------------------------------------------------------------------

    def validate_anvisa_registration(self, reg_number: str) -> ValidationResult:
        """Validate a single ANVISA registration number (9-digit numeric)."""
        reg = str(reg_number).strip()
        if not re.match(r"^\d{9}$", reg):
            return ValidationResult(
                False, 0, errors=[f"Registro ANVISA inválido: {reg} (esperado 9 dígitos)"]
            )
        valid_first = {"1", "2", "3", "7", "8", "9"}
        if reg[0] not in valid_first:
            return ValidationResult(
                True, 70, warnings=[f"Registro {reg}: primeiro dígito {reg[0]} incomum"]
            )
        return ValidationResult(True, 100)

    # ------------------------------------------------------------------
    # Full DataFrame validation
    # ------------------------------------------------------------------

    def validate_dataframe(self, df: pd.DataFrame, module: str) -> ValidationResult:
        """
        Orchestrate all validators for a given module.
        module: "imports_data" | "anvisa_data"
        """
        if df.empty:
            return ValidationResult(True, 100, warnings=["DataFrame vazio — sem dados para validar"])

        sub_results = []
        all_errors, all_warnings = [], []

        if module == "imports_data":
            key_cols = ["co_ncm", "co_pais", "co_mes", "sg_uf_ncm", "co_via"]

            if "co_ncm" in df.columns:
                r = self.validate_ncm_series(df["co_ncm"].astype(str))
                sub_results.append(r)
                all_errors += r.errors; all_warnings += r.warnings

            if "vl_fob" in df.columns:
                r = self.validate_fob_series(df["vl_fob"])
                sub_results.append(r)
                all_errors += r.errors; all_warnings += r.warnings

            if "periodo" in df.columns:
                r = self.validate_dates_series(df["periodo"])
                sub_results.append(r)
                all_errors += r.errors; all_warnings += r.warnings

                # Freshness check
                try:
                    last = pd.to_datetime(df["periodo"]).max()
                    if pd.notna(last):
                        r2 = self.validate_freshness(last.to_pydatetime())
                        sub_results.append(r2)
                        all_errors += r2.errors; all_warnings += r2.warnings
                except Exception:
                    pass

            if "co_pais" in df.columns:
                r = self.validate_country_codes(df["co_pais"].astype(str))
                sub_results.append(r)
                all_errors += r.errors; all_warnings += r.warnings

            r = self.validate_duplicates(df, key_cols)
            sub_results.append(r)
            all_errors += r.errors; all_warnings += r.warnings

        elif module == "anvisa_data":
            reg_col = next((c for c in df.columns if "registro" in c.lower()), None)
            if reg_col:
                sample = df[reg_col].dropna().head(100).astype(str)
                bad = sample[~sample.str.match(r"^\d{9}$")]
                if len(bad) > 0:
                    all_errors.append(f"Registros ANVISA inválidos: {len(bad)} (amostra)")
                    sub_results.append(ValidationResult(False, 60, errors=all_errors))
                else:
                    sub_results.append(ValidationResult(True, 100))

            date_col = next((c for c in df.columns if "vencimento" in c.lower() or "data" in c.lower()), None)
            if date_col:
                r = self.validate_dates_series(df[date_col])
                sub_results.append(r)
                all_errors += r.errors; all_warnings += r.warnings

        if not sub_results:
            return ValidationResult(True, 100, warnings=["Nenhuma validação aplicável"])

        avg_score = int(sum(r.score for r in sub_results) / len(sub_results))
        passed = all(r.passed for r in sub_results)

        return ValidationResult(
            passed=passed,
            score=avg_score,
            errors=all_errors,
            warnings=all_warnings,
            details={"module": module, "row_count": len(df), "checks_run": len(sub_results)},
        )
