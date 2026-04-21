"""
cmed_parser.py
==============
PharmaIntel BR — Parser da Tabela CMED/ANVISA.

Lê o arquivo xlsx oficial da CMED (Câmara de Regulação do Mercado de Medicamentos)
e retorna preços regulados por molécula:
- PF (Preço de Fábrica) = equivale ao PMVG (Preço Máx. Venda ao Governo)
- PMC (Preço Máximo ao Consumidor) = preço máximo em farmácias

Fonte: https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos
Arquivo: data/raw/cmed_precos.xlsx (baixado mensalmente)

Nota: Os preços na tabela são por EMBALAGEM (conjunto de unidades).
      Este módulo calcula estatísticas sobre todas as apresentações da molécula.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CMED_FILE = Path(__file__).resolve().parents[2] / "data" / "raw" / "cmed_precos.xlsx"

# Row where column headers are (0-indexed)
HEADER_ROW = 41

# Column indices in the CMED xlsx
COL_SUBSTANCIA  = 0
COL_LABORATORIO = 2
COL_PRODUTO     = 8
COL_APRESENTACAO = 9
COL_PF_SEM      = 13   # PF Sem Impostos (equivalente PMVG — preço ao governo)
COL_PMC_0       = 40   # PMC 0% (ICMS 0%, usado para uso hospitalar/governo)
COL_RESTRICAO   = 65   # Restrição Hospitalar


def _to_float(val) -> float:
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, AttributeError):
        return 0.0


@lru_cache(maxsize=1)
def _load_cmed() -> dict[str, list[dict]]:
    """
    Carrega e indexa a tabela CMED por substância (cached na primeira chamada).
    Retorna dict: substância_lower → lista de apresentações com preços.
    """
    if not CMED_FILE.exists():
        logger.warning("CMED xlsx não encontrado em %s", CMED_FILE)
        return {}

    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl não instalado — execute: pip install openpyxl")
        return {}

    logger.info("Carregando tabela CMED: %s", CMED_FILE)
    try:
        wb = openpyxl.load_workbook(str(CMED_FILE), read_only=True, data_only=True)
        ws = wb.active
    except Exception as exc:
        logger.error("Erro ao abrir CMED xlsx: %s", exc)
        return {}

    index: dict[str, list[dict]] = {}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i <= HEADER_ROW:
            continue

        substancia = str(row[COL_SUBSTANCIA] or "").strip()
        if not substancia or substancia.upper() == "SUBSTÂNCIA":
            continue

        pf  = _to_float(row[COL_PF_SEM])
        pmc = _to_float(row[COL_PMC_0])

        if pf <= 0:
            continue  # Skip entries without valid price

        key = substancia.lower()
        if key not in index:
            index[key] = []

        index[key].append({
            "substancia":   substancia,
            "laboratorio":  str(row[COL_LABORATORIO] or "").strip(),
            "produto":      str(row[COL_PRODUTO]     or "").strip(),
            "apresentacao": str(row[COL_APRESENTACAO] or "").strip(),
            "pf":           pf,
            "pmc":          pmc,
            "restricao_hospitalar": str(row[COL_RESTRICAO] or "").strip(),
        })

    wb.close()
    logger.info("CMED carregada: %d substâncias únicas", len(index))
    return index


def _find_molecule(descricao: str) -> tuple[str, list[dict]]:
    """
    Busca a molécula na tabela CMED (exact match, depois parcial).
    Retorna (chave_encontrada, lista_de_apresentações).
    """
    index = _load_cmed()
    keyword = descricao.lower().strip()

    # 1. Exact match
    if keyword in index:
        return keyword, index[keyword]

    # 2. Partial match — keyword contained in CMED key
    for key, items in index.items():
        if keyword in key:
            return key, items

    # 3. CMED key contained in keyword (e.g. user typed "insulina glargina 300ui")
    for key, items in index.items():
        if key in keyword:
            return key, items

    return "", []


def get_price_summary_cmed(descricao: str) -> Optional[dict]:
    """
    Retorna resumo de preços CMED para a molécula.

    Returns:
        dict com pf_min, pf_max, pf_medio, pmc_min, pmc_max, pmc_medio,
        total_apresentacoes, ou None se não encontrado.
    """
    mol_key, items = _find_molecule(descricao)
    if not items:
        return None

    pf_values  = [it["pf"]  for it in items if it["pf"]  > 0]
    pmc_values = [it["pmc"] for it in items if it["pmc"] > 0]

    if not pf_values:
        return None

    pf_min  = min(pf_values)
    pf_max  = max(pf_values)
    pf_med  = round(sum(pf_values) / len(pf_values), 4)

    pmc_min = min(pmc_values) if pmc_values else 0
    pmc_max = max(pmc_values) if pmc_values else 0
    pmc_med = round(sum(pmc_values) / len(pmc_values), 4) if pmc_values else 0

    # Apresentação de referência (menor PF — menor embalagem / mais próximo da unidade)
    ref = min(items, key=lambda x: x["pf"])

    labs = list({it["laboratorio"] for it in items if it["laboratorio"]})[:5]

    return {
        "substancia":          mol_key,
        "apresentacao_ref":    ref["apresentacao"],
        "laboratorio_ref":     ref["laboratorio"],
        "pf_min":              pf_min,
        "pf_max":              pf_max,
        "pf_medio":            pf_med,
        "pmc_min":             pmc_min,
        "pmc_max":             pmc_max,
        "pmc_medio":           pmc_med,
        "total_apresentacoes": len(items),
        "laboratorios":        labs,
        "fonte":               "CMED/ANVISA — Tabela de Preços Regulados",
        "arquivo":             "Publicada em 16/04/2026",
    }


def search_by_molecule(descricao: str, limit: int = 10) -> list[dict]:
    """
    Retorna lista de apresentações para a molécula (para tabelas detalhadas).
    """
    _, items = _find_molecule(descricao)
    return items[:limit]
