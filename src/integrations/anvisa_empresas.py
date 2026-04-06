"""
anvisa_empresas.py
==================
Extrai e estrutura dados de empresas detentoras de registro a partir dos
42.926 registros ANVISA abertos.

Campos extraídos de EMPRESA_DETENTORA_REGISTRO (formato: "CNPJ - RAZÃO SOCIAL"):
    cnpj, razao_social

Saídas produzidas:
    empresas_anvisa.parquet     → perfil por empresa (registros, status, categorias)
    ncm_empresa_link.parquet    → linkage NCM × empresa via classe terapêutica

Metodologia do linkage NCM × empresa
--------------------------------------
O Comex Stat público (bulk CSV) não inclui o CNPJ do importador — apenas NCM,
país de origem e valores. Para estimar quais empresas importam quais NCMs,
usamos a classe terapêutica dos produtos registrados pela empresa na ANVISA e
cruzamos com um mapeamento curado NCM → palavras-chave terapêuticas (Chapter 30).

Importante: esse é um linkage probabilístico baseado em categoria de produto,
NOT dados de importação real por empresa.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# ---------------------------------------------------------------------------
# NCM → therapeutic keyword mapping (Chapter 30, top NCMs)
# Source: TEC/NCM official descriptions + ANVISA therapeutic classes
# ---------------------------------------------------------------------------
NCM_TERAPEUTICO_MAP: dict[str, list[str]] = {
    "30021590": ["IMUNOLOGICO", "ANTICORPO", "MONOCLON", "BIOLOGICO", "IMUNOMODULADOR",
                 "CITOCINA", "INTERLEUCINA", "INTERFERON", "IMUNOSSUPRESSOR"],
    "30049069": ["HORMONIO", "ENDOCRINO", "HORM", "TIREOIDE", "CORTICOID", "ESTEROIDE",
                 "INSULINA", "GLUCAGON", "ANTIDIABETICO", "HIPOGLICEMIANTE"],
    "30049079": ["ANTINEOPLASICO", "ONCOLOGICO", "QUIMIOTERAPICO", "ANTITUMORAL",
                 "ANTICANCER", "ANTILEUCEMICO", "CITOTOXIC"],
    "30043929": ["INSULINA", "GLP", "GLUCAGON", "PEPTIDEO", "POLIPEPTIDEO",
                 "HORMONIO POLIPEPTIDICO", "SOMATOTROPIN", "ERITROPOIETIN"],
    "30024129": ["VACINA", "IMUNIZANTE", "VACIN"],
    "30049099": ["ANTIBIOTICO", "ANTIMICROBIANO", "ANTIFUNGICO", "ANTIPARASITARIO",
                 "ANTIPROTOZOARIO", "ANTIVIRAIS", "ANTIVIRAL"],
    "30021520": ["ANTICORPO MONOCLONAL", "MONOCLON", "BEVACIZUMAB", "TRASTUZUMAB",
                 "RITUXIMAB", "ADALIMUMAB", "INFLIXIMAB"],
    "30049059": ["VITAMINA", "PROVITAMINA", "VITAMINICO", "SUPLEMENTO VITAMINICO"],
    "30021235": ["IMUNOGLOBULINA", "GLOBULINA", "IMMUNOGLOBULIN"],
    "30024992": ["VACINA", "TOXINA", "CULTURA MICROBIANA", "TOXOIDE"],
    "30049019": ["ANTIBIOTICO", "CEFALOSPORINA", "PENICILINA", "AMINOGLICOSIDEO",
                 "MACROLIDEO", "QUINOLONA", "SULFONAMIDA"],
    "30049031": ["INSULINA", "ANTIDIABETICO", "HIPOGLICEMIANTE"],
    "30045000": ["VITAMINA", "VITAMINICO", "PROVITAMINA"],
    "30043100": ["INSULINA"],
    "30049089": ["ANTINEOPLASICO", "IMUNOMODULADOR", "IMUNOSSUPRESSOR",
                 "ANTIRREJEICAO", "CICLOSPORINA", "TACROLIMO"],
}

# Reverse: keyword → list of NCMs
_KEYWORD_TO_NCMS: dict[str, list[str]] = {}
for ncm, keywords in NCM_TERAPEUTICO_MAP.items():
    for kw in keywords:
        _KEYWORD_TO_NCMS.setdefault(kw, []).append(ncm)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
CNPJ_RE = re.compile(r"^\s*(\d{14})\s*-\s*(.+)$")


def _parse_empresa(raw: str) -> tuple[str, str]:
    """Extract (cnpj, razao_social) from 'CNPJ - RAZÃO SOCIAL' string."""
    if not isinstance(raw, str):
        return ("", "")
    m = CNPJ_RE.match(raw.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Fallback: try splitting on first " - "
    parts = raw.split(" - ", 1)
    if len(parts) == 2 and parts[0].strip().isdigit():
        return parts[0].strip(), parts[1].strip()
    return ("", raw.strip())


def _format_cnpj(cnpj: str) -> str:
    """Format raw 14-digit CNPJ as XX.XXX.XXX/XXXX-XX."""
    c = re.sub(r"\D", "", cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj


def _status_group(situacao: str) -> str:
    s = str(situacao).strip().lower()
    if s in ("ativo", "válido", "valido"):
        return "Ativo"
    if s in ("cancelado", "revogado", "cancelado por decisão judicial"):
        return "Cancelado"
    return "Inativo"


def _ncms_from_classe(classe: str) -> list[str]:
    """Return likely NCM codes for a given therapeutic class string."""
    if not isinstance(classe, str):
        return []
    upper = classe.upper()
    matched: set[str] = set()
    for kw, ncms in _KEYWORD_TO_NCMS.items():
        if kw in upper:
            matched.update(ncms)
    return sorted(matched)


def _vencimento_status(raw: str) -> str:
    """Classify vencimento date as Vigente / Vencendo / Vencido."""
    if not isinstance(raw, str) or not raw.strip():
        return "Sem data"
    try:
        # Format may be MMYYYY or DD/MM/YYYY
        raw = raw.strip()
        if re.match(r"^\d{6}$", raw):          # MMYYYY
            mes, ano = int(raw[:2]), int(raw[2:])
            exp = date(ano, mes, 1)
        else:
            exp = pd.to_datetime(raw, dayfirst=True, errors="coerce")
            if pd.isna(exp):
                return "Sem data"
            exp = exp.date()
        today = date.today()
        days = (exp - today).days
        if days < 0:
            return "Vencido"
        if days <= 180:
            return "Vencendo em 6 meses"
        return "Vigente"
    except Exception:
        return "Sem data"


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------
def build_empresa_dataset(anvisa_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build company and NCM-linkage datasets from raw ANVISA DataFrame.

    Args:
        anvisa_df: Raw ANVISA medications DataFrame (from fetch_medicamentos_registrados)

    Returns:
        (empresas_df, ncm_link_df)
    """
    df = anvisa_df.copy()

    # ── Parse CNPJ + razão social ──────────────────────────────────────────
    # anvisa.py normalizes EMPRESA_DETENTORA_REGISTRO → "empresa"
    empresa_col = next((c for c in ["empresa", "empresa_detentora_registro"] if c in df.columns), None)
    if empresa_col is None:
        logger.error("No company column found. Available: %s", list(df.columns))
        return pd.DataFrame(), pd.DataFrame()

    parsed = df[empresa_col].apply(
        lambda x: _parse_empresa(str(x)) if pd.notna(x) else ("", "")
    )
    df["cnpj"]         = parsed.apply(lambda t: t[0])
    df["cnpj_fmt"]     = df["cnpj"].apply(_format_cnpj)
    df["razao_social"] = parsed.apply(lambda t: t[1])

    # ── Status grouping ────────────────────────────────────────────────────
    status_col = next((c for c in ["situacao_registro", "situacao"] if c in df.columns), None)
    if status_col:
        df["status_grupo"] = df[status_col].apply(_status_group)
    else:
        df["status_grupo"] = "Desconhecido"

    # ── Vencimento classification ──────────────────────────────────────────
    venc_col = next((c for c in ["data_vencimento_registro", "vencimento"] if c in df.columns), None)
    if venc_col:
        df["vencimento_status"] = df[venc_col].apply(_vencimento_status)
    else:
        df["vencimento_status"] = "Sem data"

    # ── Categoria normalization ────────────────────────────────────────────
    cat_col = next((c for c in ["categoria_regulatoria"] if c in df.columns), None)
    if cat_col:
        df["categoria"] = df[cat_col].str.strip().str.title()
    else:
        df["categoria"] = "Desconhecido"

    # ── NCM linkage per row ────────────────────────────────────────────────
    classe_col = next((c for c in ["classe_terapeutica"] if c in df.columns), None)
    if classe_col:
        df["ncms_estimados"] = df[classe_col].apply(lambda c: _ncms_from_classe(str(c)))
    else:
        df["ncms_estimados"] = [[] for _ in range(len(df))]

    # ── Build empresa-level profile ────────────────────────────────────────
    grp = df.groupby(["cnpj", "razao_social"])

    empresa_rows = []
    for (cnpj, razao), sub in grp:
        if not cnpj:
            continue
        n_total   = len(sub)
        # Prefer the pre-computed 'ativo' boolean column from anvisa.py
        if "ativo" in sub.columns:
            n_ativo   = int(sub["ativo"].sum())
            n_inativo = n_total - n_ativo
            n_cancel  = 0
        else:
            n_ativo   = int((sub["status_grupo"] == "Ativo").sum())
            n_inativo = int((sub["status_grupo"] == "Inativo").sum())
            n_cancel  = int((sub["status_grupo"] == "Cancelado").sum())
        n_venc    = int((sub["vencimento_status"] == "Vencendo em 6 meses").sum())
        n_vencido = int((sub["vencimento_status"] == "Vencido").sum())

        cat_col2  = next((c for c in ["categoria", "categoria_regulatoria"] if c in sub.columns), None)
        categorias = sub[cat_col2].dropna().value_counts().to_dict() if cat_col2 else {}
        classes    = (
            sub[classe_col].dropna().str.strip().str.upper().value_counts().head(5).index.tolist()
            if classe_col else []
        )
        # Collect all estimated NCMs for this company
        all_ncms: set[str] = set()
        for lst in sub["ncms_estimados"]:
            all_ncms.update(lst)

        empresa_rows.append({
            "cnpj":             cnpj,
            "cnpj_fmt":         _format_cnpj(cnpj),
            "razao_social":     razao,
            "total_registros":  n_total,
            "registros_ativos": n_ativo,
            "registros_inativos": n_inativo,
            "registros_cancelados": n_cancel,
            "pct_conformidade": round(n_ativo / n_total * 100, 1) if n_total else 0,
            "alertas_vencendo": int(n_venc),
            "registros_vencidos": int(n_vencido),
            "categorias_produto": str(categorias),
            "principais_classes": classes[:5],
            "ncms_estimados":   sorted(all_ncms),
            "n_ncms_cobertos":  len(all_ncms),
        })

    empresas_df = pd.DataFrame(empresa_rows).sort_values("registros_ativos", ascending=False).reset_index(drop=True)
    logger.info("Empresas extraídas: %d (com CNPJ)", len(empresas_df))

    # ── Build NCM × empresa linkage table ─────────────────────────────────
    ncm_link_rows = []
    for _, row in empresas_df.iterrows():
        for ncm in row["ncms_estimados"]:
            ncm_link_rows.append({
                "co_ncm":           ncm,
                "cnpj":             row["cnpj"],
                "cnpj_fmt":         row["cnpj_fmt"],
                "razao_social":     row["razao_social"],
                "registros_ativos": row["registros_ativos"],
                "pct_conformidade": row["pct_conformidade"],
                "alertas_vencendo": row["alertas_vencendo"],
                "linkage_tipo":     "Classe terapêutica ANVISA",
            })

    ncm_link_df = pd.DataFrame(ncm_link_rows).reset_index(drop=True)
    logger.info("NCM-empresa links: %d", len(ncm_link_df))

    return empresas_df, ncm_link_df


def load_or_build(anvisa_df: pd.DataFrame, force: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load cached parquet files or rebuild from raw ANVISA data."""
    emp_path  = PROCESSED_DIR / "empresas_anvisa.parquet"
    link_path = PROCESSED_DIR / "ncm_empresa_link.parquet"

    if not force and emp_path.exists() and link_path.exists():
        logger.info("Loading cached empresa datasets")
        return pd.read_parquet(emp_path), pd.read_parquet(link_path)

    logger.info("Building empresa datasets from %d ANVISA rows...", len(anvisa_df))
    emp_df, link_df = build_empresa_dataset(anvisa_df)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    emp_df.to_parquet(emp_path,  index=False, engine="pyarrow")
    link_df.to_parquet(link_path, index=False, engine="pyarrow")
    logger.info("Saved: %s (%d rows), %s (%d rows)",
                emp_path.name, len(emp_df), link_path.name, len(link_df))

    return emp_df, link_df
