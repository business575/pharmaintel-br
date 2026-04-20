"""
pncp_fetcher.py
===============
PharmaIntel BR — Integração com o Portal Nacional de Contratações Públicas (PNCP).

Fornece acesso a:
- Atas de Registro de Preços por produto/molécula
- Contratos de compras públicas farmacêuticas
- Itens licitados com preços unitários

API pública, sem necessidade de chave de API.
Documentação: https://pncp.gov.br/api/pncp/swagger-ui.html
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://pncp.gov.br/api/consulta/v1"

SESSION = requests.Session()
SESSION.headers.update({
    "Accept": "application/json",
    "User-Agent": "PharmaIntelBR/1.0 (inteligencia-farmaceutica)",
})
SESSION.verify = False


def _get(endpoint: str, params: dict = None, retries: int = 3) -> dict | list:
    """GET request com retry e backoff."""
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, params=params, timeout=20)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            else:
                logger.warning("PNCP %s → HTTP %s", endpoint, resp.status_code)
                return {}
        except Exception as exc:
            logger.warning("PNCP request error (attempt %s): %s", attempt + 1, exc)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return {}


def buscar_atas_por_produto(
    descricao: str,
    pagina: int = 1,
    tam_pagina: int = 20,
) -> dict:
    """
    Busca Atas de Registro de Preços no PNCP por descrição de produto.
    API PNCP v1 (consulta) — requer dataInicial, dataFinal e codigoModalidadeContratacao.
    Modalidade 6 = Pregão Eletrônico (mais comum para medicamentos).

    Returns:
        dict com 'atas' (lista) e 'total'
    """
    from datetime import date, timedelta
    hoje = date.today()
    data_inicial = (hoje - timedelta(days=365)).strftime("%Y-%m-%d")
    data_final   = hoje.strftime("%Y-%m-%d")

    params = {
        "dataInicial": data_inicial,
        "dataFinal":   data_final,
        "codigoModalidadeContratacao": 6,  # Pregão Eletrônico
        "pagina":      pagina,
        "tamanhoPagina": min(tam_pagina, 20),
    }
    data = _get("/contratacoes/publicacao", params=params)

    if not data or not isinstance(data, dict):
        return {"atas": [], "total": 0, "descricao": descricao}

    atas = []
    keyword = descricao.lower()
    for item in data.get("data", []):
        objeto = str(item.get("objetoCompra", "")).lower()
        if keyword not in objeto:
            continue
        atas.append({
            "orgao": item.get("orgaoEntidade", {}).get("razaoSocial", ""),
            "uf": item.get("unidadeOrgao", {}).get("ufSigla", ""),
            "numero": item.get("numeroControlePNCP", ""),
            "objeto": item.get("objetoCompra", ""),
            "valor_total": item.get("valorTotalEstimado", 0),
            "data_publicacao": item.get("dataPublicacaoGlobal", ""),
            "data_encerramento": item.get("dataEncerramentoVigencia", ""),
            "link": f"https://pncp.gov.br/app/editais/{item.get('numeroControlePNCP', '')}",
        })

    return {
        "atas": atas,
        "total": data.get("totalRegistros", len(atas)),
        "descricao": descricao,
        "pagina": pagina,
    }


def buscar_itens_ata(numero_controle_pncp: str) -> dict:
    """
    Busca os itens (produtos com preços unitários) de uma Ata específica.

    Args:
        numero_controle_pncp: ex "00394507000104-1-000001/2025"

    Returns:
        dict com 'itens' (lista com descrição, quantidade, preço unitário)
    """
    # Formata o número para URL
    numero_url = numero_controle_pncp.replace("/", "%2F")
    data = _get(f"/atas/{numero_url}/itens", params={"pagina": 1, "tam_pagina": 500})

    if not data or "data" not in data:
        return {"itens": [], "numero": numero_controle_pncp}

    itens = []
    for item in data.get("data", []):
        itens.append({
            "numero_item": item.get("numeroItem", ""),
            "descricao": item.get("descricao", ""),
            "unidade": item.get("unidadeMedida", ""),
            "quantidade": item.get("quantidadeHomologada", 0),
            "preco_unitario": item.get("valorUnitarioHomologado", 0),
            "marca": item.get("marcaFabricante", ""),
            "fabricante": item.get("nomeFabricante", ""),
        })

    return {"itens": itens, "numero": numero_controle_pncp, "total": len(itens)}


def buscar_compras_farmaceuticas(
    ncm: str = "",
    descricao: str = "",
    ano: int = 2025,
    pagina: int = 1,
    tam_pagina: int = 20,
) -> dict:
    """
    Busca compras públicas farmacêuticas no PNCP.

    Args:
        ncm: código NCM (ex: "30049069")
        descricao: descrição do produto
        ano: ano de publicação
        pagina: página dos resultados
        tam_pagina: itens por página

    Returns:
        dict com 'compras' (lista) e 'total'
    """
    params = {
        "pagina": pagina,
        "tam_pagina": tam_pagina,
        "ano_publicacao": ano,
    }
    if descricao:
        params["descricao_item"] = descricao

    data = _get("/consulta/contratacoes/publicacao", params=params)

    if not data or "data" not in data:
        return {"compras": [], "total": 0}

    compras = []
    for item in data.get("data", []):
        compras.append({
            "orgao": item.get("orgaoEntidade", {}).get("razaoSocial", ""),
            "uf": item.get("unidadeOrgao", {}).get("ufSigla", ""),
            "tipo": item.get("tipoDocumento", ""),
            "objeto": item.get("objetoCompra", ""),
            "valor_total": item.get("valorTotalEstimado", 0),
            "data_publicacao": item.get("dataPublicacaoGlobal", ""),
            "numero_pncp": item.get("numeroControlePNCP", ""),
        })

    return {
        "compras": compras,
        "total": data.get("totalRegistros", len(compras)),
        "ano": ano,
    }
