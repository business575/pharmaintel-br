"""
pubmed_fetcher.py — PharmaIntel BR x PubMed Integration
Busca clinical trials e estudos científicos por princípio ativo ou NCM.
API pública E-utilities do NCBI (gratuita, sem autenticação obrigatória).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")  # opcional, aumenta rate limit

_HEADERS = {"User-Agent": "PharmaIntelBR/1.0 (business@globalhealthcareaccess.com)"}


# Mapa NCM → termos de busca para os principais medicamentos oncológicos
NCM_TO_TERMS: dict[str, str] = {
    "30049069": "antineoplastic heterocyclic",
    "30049079": "antineoplastic heterocyclic",
    "30049099": "antineoplastic agents",
    "30021590": "immunological products therapeutic",
    "30043929": "polypeptide hormones therapeutic",
    "30024129": "vaccine human medicine",
    "30049059": "hormonal antineoplastic",
    "30043100": "insulin therapeutic",
    "30049041": "antibiotics therapeutic",
    "30039099": "hormones therapeutic",
}


def _params_base() -> dict:
    p = {"retmode": "json", "retmax": "10"}
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY
    return p


def search_clinical_trials(
    query: str,
    max_results: int = 10,
    from_year: int = 2019,
    brazil_only: bool = False,
) -> list[dict]:
    """
    Busca clinical trials no PubMed por query livre.
    Retorna lista de artigos com título, autores, journal, ano, abstract e link.
    """
    full_query = f'({query}) AND "Clinical Trial"[Publication Type]'
    if brazil_only:
        full_query += ' AND Brazil[Affiliation]'
    full_query += f' AND {from_year}:{2026}[PDAT]'

    try:
        params = _params_base()
        params.update({
            "db": "pubmed",
            "term": full_query,
            "retmax": str(max_results),
            "sort": "relevance",
            "usehistory": "n",
        })
        r = httpx.get(ESEARCH_URL, params=params, headers=_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])
        total = int(data.get("esearchresult", {}).get("count", 0))

        if not pmids:
            return []

        time.sleep(0.4)  # respeita rate limit NCBI

        # Busca resumos
        params2 = _params_base()
        params2.update({
            "db": "pubmed",
            "id": ",".join(pmids),
        })
        r2 = httpx.get(ESUMMARY_URL, params=params2, headers=_HEADERS, timeout=15)
        r2.raise_for_status()
        summaries = r2.json().get("result", {})

        articles = []
        for pmid in pmids:
            s = summaries.get(pmid, {})
            if not s or s.get("error"):
                continue
            authors = [a.get("name", "") for a in s.get("authors", [])[:3]]
            articles.append({
                "pmid":     pmid,
                "title":    s.get("title", ""),
                "authors":  ", ".join(authors) + (" et al." if len(s.get("authors", [])) > 3 else ""),
                "journal":  s.get("source", ""),
                "year":     s.get("pubdate", "")[:4],
                "doi":      next((id_["value"] for id_ in s.get("articleids", [])
                                  if id_.get("idtype") == "doi"), ""),
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "total_count": total,
            })
        return articles

    except Exception as exc:
        logger.error("PubMed search error: %s", exc)
        return []


def search_by_active_ingredient(ingredient: str, max_results: int = 8) -> list[dict]:
    """Busca trials por princípio ativo (ex: 'semaglutida', 'pembrolizumab')."""
    return search_clinical_trials(
        query=f'"{ingredient}"[Title/Abstract]',
        max_results=max_results,
    )


def search_by_ncm(ncm: str, max_results: int = 8) -> list[dict]:
    """Busca trials usando o mapeamento NCM → termos farmacológicos."""
    terms = NCM_TO_TERMS.get(ncm, "pharmaceutical agents")
    return search_clinical_trials(
        query=terms,
        max_results=max_results,
    )


def get_total_trials_brazil(query: str) -> int:
    """Retorna total de trials no Brasil para um princípio ativo."""
    try:
        params = _params_base()
        params.update({
            "db": "pubmed",
            "term": f'({query}) AND "Clinical Trial"[Publication Type] AND Brazil[Affiliation]',
            "retmax": "0",
        })
        r = httpx.get(ESEARCH_URL, params=params, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        return int(r.json().get("esearchresult", {}).get("count", 0))
    except Exception:
        return 0
