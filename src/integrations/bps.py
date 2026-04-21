"""
bps.py
======
PharmaIntel BR — Preços de referência governamentais via CMED/ANVISA.

NOTA: O BPS (Banco de Preços em Saúde) migrou para QlikSense em 2025 e
não possui mais API REST pública. Este módulo usa:

1. CMED/ANVISA — Tabela oficial de Preços Máximos Regulados (PMC e PF/PMVG)
   Arquivo xlsx baixado mensalmente de:
   https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos

O PF (Preço de Fábrica) equivale ao PMVG (Preço Máximo de Venda ao Governo).
O PMC (Preço Máximo ao Consumidor) é o teto para farmácias.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_price_summary(
    descricao: str,
    uf: Optional[str] = None,
    ano: Optional[int] = None,
) -> dict:
    """
    Retorna preços de referência CMED/ANVISA para a molécula.

    Usa o arquivo xlsx oficial da CMED (data/raw/cmed_precos.xlsx).
    Fallback para tabela manual se o arquivo não estiver disponível.

    Returns dict com preco_minimo, preco_maximo, preco_medio, preco_mediano.
    """
    # 1. Tenta parser CMED com dados reais do xlsx
    try:
        from src.integrations.cmed_parser import get_price_summary_cmed
        cmed = get_price_summary_cmed(descricao)
        if cmed:
            pf_min  = cmed["pf_min"]
            pf_max  = cmed["pf_max"]
            pf_med  = cmed["pf_medio"]
            pmc_min = cmed["pmc_min"]
            pmc_max = cmed["pmc_max"]
            pmc_med = cmed["pmc_medio"]

            # Se não há PMC (ex: medicamentos hospitalares, uso restrito)
            # usa PF * 1.40 como estimativa
            if pmc_med == 0:
                pmc_med = round(pf_med * 1.40, 4)
                pmc_min = round(pf_min * 1.40, 4)
                pmc_max = round(pf_max * 1.40, 4)

            return {
                "produto":          descricao,
                "uf":               uf,
                "ano":              ano,
                "total_compras":    cmed["total_apresentacoes"],
                "preco_minimo":     pf_min,
                "preco_maximo":     pf_max,
                "preco_medio":      pf_med,
                "preco_mediano":    pf_med,
                "pmvg_brl":         pf_med,    # PF médio = referência PMVG
                "pmc_brl":          pmc_med,   # PMC médio = referência ao consumidor
                "pf_medio":         pf_med,
                "pmc_medio":        pmc_med,
                "unidade":          cmed["apresentacao_ref"],
                "laboratorios":     cmed["laboratorios"],
                "top_fabricantes":  cmed["laboratorios"],
                "top_orgaos":       [],
                "sample": [{
                    "descricao":      descricao,
                    "valor_unitario": pf_min,
                    "modalidade":     "PF (Preço de Fábrica / PMVG)",
                    "fonte":          cmed["fonte"],
                }],
                "fonte":  cmed["fonte"],
                "arquivo": cmed.get("arquivo", ""),
                "total_apresentacoes": cmed["total_apresentacoes"],
            }
    except Exception as exc:
        logger.warning("CMED parser error: %s — usando tabela fallback", exc)

    # 2. Fallback: tabela manual (valores de referência)
    return _get_price_fallback(descricao, uf, ano)


# ---------------------------------------------------------------------------
# Tabela fallback — valores de referência CMED (caso o xlsx não esteja disponível)
# Fonte: Tabela CMED ANVISA — valores de referência por apresentação
# ---------------------------------------------------------------------------
_REFERENCE_PRICES: dict[str, dict] = {
    "enoxaparina": {
        "unidade": "seringa 40mg/0,4mL",
        "pmvg_brl": 51.56,
        "pmc_brl":  71.94,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "insulina": {
        "unidade": "frasco 10mL/100UI",
        "pmvg_brl": 34.81,
        "pmc_brl":  52.30,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "insulina glargina": {
        "unidade": "cartucho 3mL/100UI",
        "pmvg_brl": 73.07,
        "pmc_brl":  101.95,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "adalimumabe": {
        "unidade": "seringa preenchida 40mg/0,8mL",
        "pmvg_brl": 3350.24,
        "pmc_brl":  4674.04,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "bevacizumabe": {
        "unidade": "frasco 100mg/4mL",
        "pmvg_brl": 1918.45,
        "pmc_brl":  2686.83,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "trastuzumabe": {
        "unidade": "frasco 150mg",
        "pmvg_brl": 8338.32,
        "pmc_brl":  11673.65,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "rituximabe": {
        "unidade": "frasco 100mg/10mL",
        "pmvg_brl": 3825.75,
        "pmc_brl":  5356.05,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "carboplatina": {
        "unidade": "frasco 50mg/5mL",
        "pmvg_brl": 398.86,
        "pmc_brl":  558.40,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "oxaliplatina": {
        "unidade": "frasco 50mg/10mL",
        "pmvg_brl": 1616.63,
        "pmc_brl":  2263.28,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "imunoglobulina": {
        "unidade": "frasco 5g",
        "pmvg_brl": 221.06,
        "pmc_brl":  309.48,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "heparina": {
        "unidade": "frasco 5.000UI/mL",
        "pmvg_brl": 284.44,
        "pmc_brl":  398.22,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "amoxicilina": {
        "unidade": "cápsula 500mg",
        "pmvg_brl": 0.86,   # por unidade (22.20/26 = ~0.85)
        "pmc_brl":  1.19,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "azitromicina": {
        "unidade": "comprimido 500mg",
        "pmvg_brl": 14.11,  # cx 2 comp = 28.22
        "pmc_brl":  19.69,
        "fonte": "CMED/ANVISA (fallback)",
    },
    "omeprazol": {
        "unidade": "cápsula 20mg",
        "pmvg_brl": 0.12,
        "pmc_brl":  0.35,
        "fonte": "CMED/ANVISA (fallback)",
    },
}


def _get_price_fallback(
    descricao: str,
    uf: Optional[str] = None,
    ano: Optional[int] = None,
) -> dict:
    """Retorna preço da tabela manual de fallback."""
    keyword = descricao.lower().strip()
    data = _REFERENCE_PRICES.get(keyword)

    if not data:
        for mol, info in _REFERENCE_PRICES.items():
            if keyword in mol or mol in keyword:
                data = info
                break

    if not data:
        return {
            "produto": descricao,
            "total_compras": 0,
            "mensagem": "Molécula não encontrada na tabela CMED. Consulte anvisa.gov.br/cmed",
        }

    pmvg = data["pmvg_brl"]
    pmc  = data["pmc_brl"]

    return {
        "produto":         descricao,
        "uf":              uf,
        "ano":             ano,
        "total_compras":   1,
        "preco_minimo":    pmvg,
        "preco_maximo":    pmc,
        "preco_medio":     round((pmvg + pmc) / 2, 4),
        "preco_mediano":   round((pmvg + pmc) / 2, 4),
        "pmvg_brl":        pmvg,
        "pmc_brl":         pmc,
        "unidade":         data["unidade"],
        "top_fabricantes": [],
        "top_orgaos":      [],
        "sample": [{
            "descricao":      descricao,
            "valor_unitario": pmvg,
            "modalidade":     "PF/PMVG (Preço Fábrica / Máx. Venda Governo)",
            "fonte":          data["fonte"],
        }],
        "fonte": "CMED/ANVISA — Tabela de Preços Regulados (fallback)",
    }


class BPSError(Exception):
    pass


def search_precos(descricao: str, uf=None, ano=None, limit: int = 100):
    """Compatibilidade — retorna DataFrame com dados CMED."""
    try:
        import pandas as pd
        summary = get_price_summary(descricao, uf=uf, ano=ano)
        if summary.get("total_compras", 0) == 0:
            return pd.DataFrame()
        return pd.DataFrame(summary.get("sample", []))
    except Exception:
        import pandas as pd
        return pd.DataFrame()
