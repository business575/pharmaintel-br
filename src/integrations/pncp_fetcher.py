"""
pncp_fetcher.py
===============
PharmaIntel BR — Integração com o Portal Nacional de Contratações Públicas (PNCP).

Fornece acesso a:
- Atas de Registro de Preços com itens e preços unitários
- Filtragem por molécula/produto nos itens das atas

API pública, sem necessidade de chave de API.
Documentação: https://pncp.gov.br/api/pncp/swagger-ui.html

IMPORTANTE: O endpoint /v1/atas NÃO tem filtro por palavra-chave no servidor.
A estratégia correta é:
  1. Buscar atas com keywords farmacêuticas genéricas no objetoContratacao
  2. Buscar os itens de cada ata encontrada
  3. Filtrar itens pelo nome da molécula

"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL     = "https://pncp.gov.br/api/consulta/v1"
BASE_PNCP_V1 = "https://pncp.gov.br/api/pncp/v1"

SESSION = requests.Session()
SESSION.headers.update({
    "Accept": "application/json",
    "User-Agent": "PharmaIntelBR/1.0 (inteligencia-farmaceutica)",
})
SESSION.verify = False

# Palavras-chave farmacêuticas para identificar atas farmacêuticas
_PHARMA_KEYWORDS = [
    "medicamento", "farmac", "hospitalar", "insumo farmac",
    "registro de preços de medicamentos", "material médico",
]


def _get(endpoint: str, params: dict = None, retries: int = 2, timeout: int = 15) -> dict | list:
    """GET request com retry e backoff."""
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, params=params, timeout=timeout)
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
                time.sleep(1)
    return {}


def _is_pharma_ata(objeto: str) -> bool:
    """Verifica se o objeto da ata parece ser farmacêutico."""
    o = objeto.lower()
    return any(kw in o for kw in _PHARMA_KEYWORDS)


def buscar_atas_por_produto(
    descricao: str,
    pagina: int = 1,
    tam_pagina: int = 20,
) -> dict:
    """
    Busca Atas de Registro de Preços vigentes no PNCP contendo o produto.

    Estratégia:
      - Varre páginas de atas recentes
      - Identifica atas farmacêuticas pelo objetoContratacao
      - Busca itens de cada ata farmacêutica
      - Filtra itens pelo nome da molécula

    Returns:
        dict com 'atas' (lista) e 'total'
    """
    from datetime import date, timedelta
    hoje = date.today()
    data_inicial = (hoje - timedelta(days=180)).strftime("%Y%m%d")
    data_final   = hoje.strftime("%Y%m%d")

    keyword = descricao.lower().strip()
    atas_com_produto = []
    precos_encontrados = []

    # Varre até 8 páginas de atas buscando atas farmacêuticas
    for pg in range(1, 9):
        params = {
            "dataInicial":   data_inicial,
            "dataFinal":     data_final,
            "pagina":        pg,
            "tamanhoPagina": 50,
        }
        data = _get("/atas", params=params)
        if not data or not isinstance(data, dict) or not data.get("data"):
            break

        pharma_atas = [
            item for item in data.get("data", [])
            if _is_pharma_ata(str(item.get("objetoContratacao", "")))
            and not item.get("cancelado", False)
        ]

        # Para cada ata farmacêutica, busca itens e filtra pela molécula
        for ata in pharma_atas[:8]:  # max 8 atas por página para não travar
            numero = ata.get("numeroControlePNCPAta", "")
            if not numero:
                continue
            try:
                itens_resp = buscar_itens_ata(numero)
                for item in itens_resp.get("itens", []):
                    desc_item = str(item.get("descricao", "")).lower()
                    if keyword in desc_item or _partial_match(keyword, desc_item):
                        preco = float(item.get("preco_unitario", 0) or 0)
                        vigencia = str(ata.get("vigenciaFim", ""))
                        hoje_str = hoje.strftime("%Y-%m-%d")
                        # Inclui apenas atas vigentes
                        if preco > 0 and (not vigencia or vigencia >= hoje_str):
                            precos_encontrados.append(preco)
                            atas_com_produto.append({
                                "orgao":            ata.get("nomeOrgao", ""),
                                "uf":               "",
                                "numero":           numero,
                                "objeto":           ata.get("objetoContratacao", ""),
                                "valor_total":      preco,
                                "data_publicacao":  ata.get("dataPublicacaoPncp", ""),
                                "data_encerramento": vigencia,
                                "item_descricao":   item.get("descricao", ""),
                                "item_unidade":     item.get("unidade", ""),
                                "item_preco":       preco,
                                "item_marca":       item.get("marca", ""),
                                "link": f"https://pncp.gov.br/app/atas/{numero}",
                                "cancelado": False,
                            })
            except Exception:
                continue

        # Se já encontramos preços suficientes, para
        if len(precos_encontrados) >= 10:
            break

        # Se acabaram as atas
        total_regs = data.get("totalRegistros", 0)
        if pg * 50 >= total_regs:
            break

    return {
        "atas":       atas_com_produto,
        "total":      len(atas_com_produto),
        "precos":     precos_encontrados,
        "descricao":  descricao,
        "pagina":     pagina,
    }


def _partial_match(keyword: str, text: str) -> bool:
    """Match parcial para lidar com nomes compostos (ex: 'insulina glargina' em 'glargina 100ui')."""
    parts = keyword.split()
    if len(parts) > 1:
        return all(p in text for p in parts if len(p) > 3)
    return False


def buscar_itens_ata(numero_controle_pncp: str) -> dict:
    """
    Busca os itens (produtos com preços unitários) de uma Ata específica.

    Args:
        numero_controle_pncp: ex "00394507000104-1-000001/2025"

    Returns:
        dict com 'itens' (lista com descrição, quantidade, preço unitário)
    """
    numero_url = numero_controle_pncp.replace("/", "%2F")
    url = f"{BASE_PNCP_V1}/atas/{numero_url}/itens"
    try:
        resp = SESSION.get(url, params={"pagina": 1, "tamanhoPagina": 500}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
        else:
            return {"itens": [], "numero": numero_controle_pncp}
    except Exception:
        return {"itens": [], "numero": numero_controle_pncp}

    if not data or "data" not in data:
        return {"itens": [], "numero": numero_controle_pncp}

    itens = []
    for item in data.get("data", []):
        itens.append({
            "numero_item":   item.get("numeroItem", ""),
            "descricao":     item.get("descricao", ""),
            "unidade":       item.get("unidadeMedida", ""),
            "quantidade":    item.get("quantidadeHomologada", 0),
            "preco_unitario": item.get("valorUnitarioHomologado", 0),
            "marca":         item.get("marcaFabricante", ""),
            "fabricante":    item.get("nomeFabricante", ""),
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
    """
    params = {
        "pagina":     pagina,
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
            "uf":    item.get("unidadeOrgao", {}).get("ufSigla", ""),
            "tipo":  item.get("tipoDocumento", ""),
            "objeto": item.get("objetoCompra", ""),
            "valor_total": item.get("valorTotalEstimado", 0),
            "data_publicacao": item.get("dataPublicacaoGlobal", ""),
            "numero_pncp": item.get("numeroControlePNCP", ""),
        })

    return {
        "compras": compras,
        "total":   data.get("totalRegistros", len(compras)),
        "ano":     ano,
    }
