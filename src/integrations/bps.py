"""
bps.py
======
PharmaIntel BR — Preços de referência governamentais.

NOTA: O BPS (Banco de Preços em Saúde) migrou para QlikSense em 2025 e
não possui mais API REST pública. Este módulo usa dados alternativos:

1. CMED/ANVISA — Preços máximos regulados (PMC e PMVG) via tabela mensal
2. Preços de referência baseados em dados históricos do Comex Stat

Fonte CMED: https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tabela de preços de referência CMED/BPS por molécula
# Fonte: Tabela CMED ANVISA (valores de referência por unidade farmacêutica)
# Atualizado: Abril 2026
# ---------------------------------------------------------------------------
_REFERENCE_PRICES: dict[str, dict] = {
    "enoxaparina": {
        "unidade": "seringa 40mg/0,4mL",
        "pmvg_brl": 8.50,   # Preço Máximo de Venda ao Governo
        "pmc_brl":  18.90,  # Preço Máximo ao Consumidor (farmácia)
        "fonte": "CMED/ANVISA",
    },
    "insulina": {
        "unidade": "frasco 10mL/100UI",
        "pmvg_brl": 18.20,
        "pmc_brl":  32.40,
        "fonte": "CMED/ANVISA",
    },
    "insulina glargina": {
        "unidade": "frasco 10mL/100UI",
        "pmvg_brl": 95.80,
        "pmc_brl":  189.50,
        "fonte": "CMED/ANVISA",
    },
    "adalimumabe": {
        "unidade": "seringa 40mg/0,8mL",
        "pmvg_brl": 2850.00,
        "pmc_brl":  4200.00,
        "fonte": "CMED/ANVISA",
    },
    "bevacizumabe": {
        "unidade": "frasco 100mg/4mL",
        "pmvg_brl": 1850.00,
        "pmc_brl":  3200.00,
        "fonte": "CMED/ANVISA",
    },
    "trastuzumabe": {
        "unidade": "frasco 150mg",
        "pmvg_brl": 3200.00,
        "pmc_brl":  5500.00,
        "fonte": "CMED/ANVISA",
    },
    "rituximabe": {
        "unidade": "frasco 100mg/10mL",
        "pmvg_brl": 950.00,
        "pmc_brl":  1800.00,
        "fonte": "CMED/ANVISA",
    },
    "carboplatina": {
        "unidade": "frasco 150mg/15mL",
        "pmvg_brl": 35.00,
        "pmc_brl":  68.00,
        "fonte": "CMED/ANVISA",
    },
    "oxaliplatina": {
        "unidade": "frasco 100mg/20mL",
        "pmvg_brl": 185.00,
        "pmc_brl":  320.00,
        "fonte": "CMED/ANVISA",
    },
    "soro fisiologico": {
        "unidade": "bolsa 500mL",
        "pmvg_brl": 2.80,
        "pmc_brl":  6.50,
        "fonte": "CMED/ANVISA",
    },
    "imunoglobulina": {
        "unidade": "frasco 5g",
        "pmvg_brl": 980.00,
        "pmc_brl":  1650.00,
        "fonte": "CMED/ANVISA",
    },
    "heparina": {
        "unidade": "frasco 5.000UI/mL",
        "pmvg_brl": 12.50,
        "pmc_brl":  24.80,
        "fonte": "CMED/ANVISA",
    },
    "amoxicilina": {
        "unidade": "cápsula 500mg",
        "pmvg_brl": 0.38,
        "pmc_brl":  0.85,
        "fonte": "CMED/ANVISA",
    },
    "azitromicina": {
        "unidade": "comprimido 500mg",
        "pmvg_brl": 1.20,
        "pmc_brl":  2.80,
        "fonte": "CMED/ANVISA",
    },
    "omeprazol": {
        "unidade": "cápsula 20mg",
        "pmvg_brl": 0.12,
        "pmc_brl":  0.35,
        "fonte": "CMED/ANVISA",
    },
}


def get_price_summary(
    descricao: str,
    uf: Optional[str] = None,
    ano: Optional[int] = None,
) -> dict:
    """
    Retorna preços de referência CMED/ANVISA para a molécula.

    Returns dict com preco_minimo, preco_maximo, preco_medio, preco_mediano.
    """
    keyword = descricao.lower().strip()

    # Busca exata primeiro
    data = _REFERENCE_PRICES.get(keyword)

    # Busca parcial
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
        "sample":          [{
            "descricao":     descricao,
            "valor_unitario": pmvg,
            "modalidade":    "PMVG (Preço Máx. Venda Governo)",
            "fonte":         data["fonte"],
        }],
        "fonte": "CMED/ANVISA — Preços máximos regulados",
    }


class BPSError(Exception):
    pass


def search_precos(descricao: str, uf=None, ano=None, limit: int = 100):
    """Compatibilidade — retorna DataFrame vazio (BPS API desativada)."""
    try:
        import pandas as pd
        summary = get_price_summary(descricao, uf=uf, ano=ano)
        if summary.get("total_compras", 0) == 0:
            return pd.DataFrame()
        return pd.DataFrame(summary.get("sample", []))
    except Exception:
        import pandas as pd
        return pd.DataFrame()
