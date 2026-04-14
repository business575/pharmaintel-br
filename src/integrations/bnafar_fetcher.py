"""
bnafar_fetcher.py
=================
PharmaIntel BR — Integração com o BNAFAR (Banco Nacional de Preços na Área de Saúde).

Fornece acesso a:
- Preços de medicamentos em compras públicas de saúde
- Histórico de preços por produto/princípio ativo
- Comparativo de preços por UF e órgão

API pública do Ministério da Saúde, sem necessidade de chave de API.
Portal: https://bnafar.saude.gov.br
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://bnafar.saude.gov.br/api"

SESSION = requests.Session()
SESSION.headers.update({
    "Accept": "application/json",
    "User-Agent": "PharmaIntelBR/1.0 (inteligencia-farmaceutica)",
})
SESSION.verify = False


def _get(endpoint: str, params: dict = None, retries: int = 3) -> dict | list:
    """GET request com retry e backoff exponencial."""
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
                logger.warning("BNAFAR %s → HTTP %s", endpoint, resp.status_code)
                return {}
        except Exception as exc:
            logger.warning("BNAFAR request error (attempt %s): %s", attempt + 1, exc)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return {}


def buscar_precos_medicamento(
    nome: str,
    pagina: int = 1,
    tam_pagina: int = 20,
) -> dict:
    """
    Busca preços de medicamentos em compras públicas pelo BNAFAR.

    Args:
        nome: nome do medicamento ou princípio ativo (ex: "insulina glargina")
        pagina: página dos resultados
        tam_pagina: itens por página

    Returns:
        dict com 'precos' (lista) e 'estatisticas'
    """
    params = {
        "nome": nome,
        "page": pagina - 1,  # BNAFAR usa 0-indexed
        "size": tam_pagina,
    }
    data = _get("/v1/medicamentos", params=params)

    if not data:
        return {"precos": [], "total": 0, "nome": nome}

    # Tenta formato de lista direta
    items = data if isinstance(data, list) else data.get("content", data.get("data", []))

    precos = []
    valores = []
    for item in items:
        preco_unit = item.get("precoUnitario", item.get("valorUnitario", 0))
        if preco_unit:
            valores.append(float(preco_unit))
        precos.append({
            "produto": item.get("nomeProduto", item.get("descricao", "")),
            "principio_ativo": item.get("principioAtivo", ""),
            "apresentacao": item.get("apresentacao", ""),
            "laboratorio": item.get("laboratorio", item.get("fabricante", "")),
            "orgao_comprador": item.get("orgao", item.get("razaoSocial", "")),
            "uf": item.get("uf", ""),
            "preco_unitario": preco_unit,
            "quantidade": item.get("quantidade", 0),
            "data_compra": item.get("dataCompra", item.get("data", "")),
            "numero_processo": item.get("numeroProcesso", ""),
        })

    estatisticas = {}
    if valores:
        estatisticas = {
            "preco_minimo": min(valores),
            "preco_maximo": max(valores),
            "preco_medio": round(sum(valores) / len(valores), 4),
            "total_registros": len(valores),
        }

    total = data.get("totalElements", data.get("total", len(precos))) if isinstance(data, dict) else len(precos)

    return {
        "precos": precos,
        "estatisticas": estatisticas,
        "total": total,
        "nome": nome,
    }


def buscar_precos_por_principio_ativo(principio_ativo: str) -> dict:
    """
    Busca preços consolidados por princípio ativo no BNAFAR.

    Args:
        principio_ativo: ex "insulina glargina", "metformina", "amoxicilina"

    Returns:
        dict com preços mín/máx/médio e lista de compras recentes
    """
    params = {
        "principioAtivo": principio_ativo,
        "page": 0,
        "size": 50,
    }
    data = _get("/v1/medicamentos", params=params)

    if not data:
        # Tenta endpoint alternativo
        data = _get("/v1/precos", params={"q": principio_ativo, "size": 50})

    if not data:
        return {
            "disponivel": False,
            "mensagem": "Dados não disponíveis no BNAFAR para este princípio ativo.",
            "principio_ativo": principio_ativo,
        }

    items = data if isinstance(data, list) else data.get("content", data.get("data", []))

    valores = []
    compras_recentes = []
    for item in items:
        preco = item.get("precoUnitario", item.get("valorUnitario", 0))
        if preco:
            valores.append(float(preco))
            compras_recentes.append({
                "orgao": item.get("orgao", ""),
                "uf": item.get("uf", ""),
                "preco_unitario": preco,
                "laboratorio": item.get("laboratorio", ""),
                "data": item.get("dataCompra", ""),
            })

    if not valores:
        return {
            "disponivel": False,
            "mensagem": f"Nenhum preço encontrado no BNAFAR para '{principio_ativo}'.",
            "principio_ativo": principio_ativo,
        }

    compras_recentes.sort(key=lambda x: x.get("data", ""), reverse=True)

    return {
        "disponivel": True,
        "principio_ativo": principio_ativo,
        "estatisticas": {
            "preco_minimo": min(valores),
            "preco_maximo": max(valores),
            "preco_medio": round(sum(valores) / len(valores), 4),
            "total_registros": len(valores),
        },
        "compras_recentes": compras_recentes[:10],
    }
