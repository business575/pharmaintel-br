"""
patent_fetcher.py
=================
PharmaIntel BR — Atualização automática de patentes farmacêuticas.

Fontes:
    1. EPO Open Patent Services (OPS) — via API REST gratuita (requer registro)
       Env vars: EPO_OPS_KEY, EPO_OPS_SECRET
       Registro: https://developers.epo.org/

    2. INPI pePI — scraping leve do portal público
       URL: https://busca.inpi.gov.br/pePI/

    3. Fallback: mantém dados do JSON sem alteração

Uso:
    from src.integrations.patent_fetcher import refresh_patents
    result = refresh_patents()  # atualiza data/patents.json
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

PATENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "patents.json"

# ---------------------------------------------------------------------------
# EPO OPS client
# ---------------------------------------------------------------------------

EPO_TOKEN_URL  = "https://ops.epo.org/3.2/auth/accesstoken"
EPO_BIBLIO_URL = "https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{ep_number}/biblio"
EPO_LEGAL_URL  = "https://ops.epo.org/3.2/rest-services/legal/{ep_number}"
EPO_SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search"


def _epo_token(key: str, secret: str) -> Optional[str]:
    """Obtain OAuth2 access token from EPO OPS."""
    try:
        resp = requests.post(
            EPO_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(key, secret),
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as exc:
        logger.warning("EPO OPS token error: %s", exc)
        return None


def _epo_fetch_biblio(ep_number: str, token: str) -> Optional[dict]:
    """
    Fetch bibliographic data for a patent from EPO OPS.
    Returns dict with keys: expiry_date, status, title.
    """
    url = EPO_BIBLIO_URL.format(ep_number=ep_number.upper())
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=20,
            verify=False,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

        # Navigate EPO OPS JSON — structure: ops:world-patent-data → ops:biblio-search…
        docs = (
            data.get("ops:world-patent-data", {})
            .get("ops:biblio-search", {})
            .get("ops:search-result", {})
            .get("ops:publication-reference", [])
        )
        # If direct biblio endpoint, path differs
        pub_ref = (
            data.get("ops:world-patent-data", {})
            .get("exchange-documents", {})
            .get("exchange-document", {})
        )
        if not pub_ref:
            return None

        # Extract expiry date from legal events if present
        return _parse_epo_biblio(pub_ref)
    except Exception as exc:
        logger.warning("EPO biblio fetch error (%s): %s", ep_number, exc)
        return None


def _parse_epo_biblio(doc: dict) -> dict:
    """Parse EPO OPS exchange-document into simplified dict."""
    result: dict = {}

    # Title
    titles = doc.get("bibliographic-data", {}).get("invention-title", [])
    if isinstance(titles, dict):
        titles = [titles]
    for t in titles:
        if isinstance(t, dict) and t.get("@lang", "") == "en":
            result["title"] = t.get("$", "")
            break

    # Priority / application date → used to estimate expiry (20y from priority)
    priority = doc.get("bibliographic-data", {}).get("priority-claims", {}).get("priority-claim", [])
    if isinstance(priority, dict):
        priority = [priority]
    for pc in priority:
        pdate = pc.get("date", {}).get("$", "")
        if pdate and len(pdate) == 8:
            try:
                pdt = date(int(pdate[:4]), int(pdate[4:6]), int(pdate[6:8]))
                result["priority_date"] = pdt.isoformat()
                # Patent term: 20 years from priority (approximate)
                exp_year = pdt.year + 20
                result["estimated_expiry_from_priority"] = f"{exp_year}-{pdate[4:6]}-{pdate[6:8]}"
                break
            except ValueError:
                pass

    return result


def _epo_search_by_inn(inn: str, token: str) -> Optional[str]:
    """Search EPO OPS for a patent by INN drug name. Returns EP number if found."""
    try:
        query = f'ct="{inn}"'
        resp = requests.get(
            EPO_SEARCH_URL,
            params={"q": query, "Range": "1-5"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=20,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
        refs = (
            data.get("ops:world-patent-data", {})
            .get("ops:biblio-search", {})
            .get("ops:search-result", {})
            .get("ops:publication-reference", [])
        )
        if isinstance(refs, dict):
            refs = [refs]
        for ref in refs:
            doc_id = ref.get("document-id", {})
            if isinstance(doc_id, list):
                doc_id = doc_id[0]
            country = doc_id.get("country", {}).get("$", "")
            number  = doc_id.get("doc-number", {}).get("$", "")
            if country == "EP" and number:
                return f"EP{number}"
        return None
    except Exception as exc:
        logger.debug("EPO search error (%s): %s", inn, exc)
        return None


# ---------------------------------------------------------------------------
# INPI scraper (leve — apenas verifica status público)
# ---------------------------------------------------------------------------

INPI_SEARCH_URL = "https://busca.inpi.gov.br/pePI/servlet/PatenteServlet"


def _inpi_check_pi(pi_number: str) -> Optional[dict]:
    """
    Query INPI pePI portal for a patent by PI number.
    Returns dict with keys: situacao, vigencia_ate.
    """
    if not pi_number:
        return None
    try:
        resp = requests.get(
            INPI_SEARCH_URL,
            params={"Action": "detail", "CodPedido": pi_number},
            headers={"User-Agent": "PharmaIntelBR/2.0 (data research)"},
            timeout=20,
            verify=False,
        )
        if resp.status_code != 200:
            return None

        text = resp.text
        # Heuristic parse — INPI returns HTML
        result: dict = {}

        import re
        # Look for "Situação" field
        situacao_match = re.search(r"Situa[çc][aã]o[:\s]+<[^>]+>([^<]+)<", text, re.IGNORECASE)
        if situacao_match:
            result["situacao"] = situacao_match.group(1).strip()

        # Look for expiry date pattern dd/mm/yyyy
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", text)
        if dates:
            # Last date pattern in the page is usually the expiry
            result["datas_encontradas"] = dates[-3:] if len(dates) >= 3 else dates

        return result if result else None
    except Exception as exc:
        logger.debug("INPI check error (%s): %s", pi_number, exc)
        return None


# ---------------------------------------------------------------------------
# Status inference from dates
# ---------------------------------------------------------------------------

def _infer_status(exp_br: str) -> str:
    """Infer patent status from expiration date string (ISO format)."""
    if not exp_br:
        return "Desconhecida"
    try:
        exp_date = date.fromisoformat(exp_br)
        today    = date.today()
        days     = (exp_date - today).days
        if days < 0:
            return "Expirada"
        if days <= 365:
            return "Vencendo em breve"
        return "Vigente"
    except ValueError:
        return "Desconhecida"


# ---------------------------------------------------------------------------
# Main refresh function
# ---------------------------------------------------------------------------

def refresh_patents(
    patents_path: Path = PATENTS_PATH,
    use_epo: bool = True,
    use_inpi: bool = True,
    delay_s: float = 1.5,
) -> dict:
    """
    Refresh patent data from EPO OPS and/or INPI portal.

    Reads patents.json, queries APIs for updated status,
    writes updated JSON back to disk.

    Args:
        patents_path: Path to patents.json
        use_epo:      Try EPO OPS API (requires EPO_OPS_KEY + EPO_OPS_SECRET env vars)
        use_inpi:     Try INPI pePI scraping for PI numbers
        delay_s:      Delay between API calls (rate limiting)

    Returns:
        Summary dict: {updated, skipped, errors, total}
    """
    if not patents_path.exists():
        logger.error("patents.json not found: %s", patents_path)
        return {"error": "patents.json not found", "updated": 0}

    with open(patents_path, encoding="utf-8") as f:
        patents: list[dict] = json.load(f)

    epo_key    = os.getenv("EPO_OPS_KEY", "")
    epo_secret = os.getenv("EPO_OPS_SECRET", "")
    epo_token  = None

    if use_epo and epo_key and epo_secret:
        logger.info("Connecting to EPO OPS…")
        epo_token = _epo_token(epo_key, epo_secret)
        if epo_token:
            logger.info("EPO OPS token obtained.")
        else:
            logger.warning("EPO OPS auth failed — falling back to JSON data.")

    summary = {"updated": 0, "skipped": 0, "errors": 0, "total": len(patents)}
    now_iso  = datetime.now(tz=timezone.utc).date().isoformat()

    for patent in patents:
        drug = patent.get("principio_ativo", "?")
        changed = False

        # ── 1. Re-infer status from stored date ──────────────────────────
        current_status = _infer_status(patent.get("patente_expiracao_br", ""))
        if current_status != patent.get("status", "") and current_status != "Desconhecida":
            logger.info("%s: status updated %s → %s", drug, patent.get("status"), current_status)
            patent["status"] = current_status
            changed = True

        # Update opportunity label based on status
        if current_status == "Expirada" and "IMEDIATA" not in patent.get("oportunidade_biossimilar", ""):
            exp_br = patent.get("patente_expiracao_br", "")
            patent["oportunidade_biossimilar"] = (
                f"IMEDIATA — patente expirou em {exp_br} no Brasil"
                if exp_br else "IMEDIATA"
            )
            changed = True

        # ── 2. Try EPO OPS for enrichment ────────────────────────────────
        ep_number = patent.get("ep_number", "")
        if use_epo and epo_token and ep_number:
            try:
                biblio = _epo_fetch_biblio(ep_number, epo_token)
                if biblio and biblio.get("priority_date"):
                    # Only update expiry if we don't have a precise date yet
                    est = biblio.get("estimated_expiry_from_priority", "")
                    if est and not patent.get("patente_expiracao_us"):
                        patent["patente_expiracao_us"] = est
                        patent["source"] = "epo_ops"
                        changed = True
                time.sleep(delay_s)
            except Exception as exc:
                logger.warning("EPO fetch failed for %s (%s): %s", drug, ep_number, exc)
                summary["errors"] += 1

        # ── 3. Try INPI for Brazilian status ─────────────────────────────
        inpi_pi = patent.get("inpi_pi", "")
        if use_inpi and inpi_pi:
            try:
                inpi_data = _inpi_check_pi(inpi_pi)
                if inpi_data:
                    situacao = inpi_data.get("situacao", "").lower()
                    if "arquiv" in situacao or "extint" in situacao or "nulo" in situacao:
                        patent["status"] = "Expirada"
                        patent["source"] = "inpi"
                        changed = True
                    elif "vigor" in situacao or "ativ" in situacao:
                        # Keep current expiry date, mark source
                        patent["source"] = "inpi"
                        changed = True
                time.sleep(delay_s)
            except Exception as exc:
                logger.warning("INPI check failed for %s (%s): %s", drug, inpi_pi, exc)
                summary["errors"] += 1

        if changed:
            patent["last_refreshed"] = now_iso
            summary["updated"] += 1
        else:
            summary["skipped"] += 1

    # Write updated JSON
    with open(patents_path, "w", encoding="utf-8") as f:
        json.dump(patents, f, ensure_ascii=False, indent=2)

    logger.info(
        "Patent refresh done: %d updated, %d skipped, %d errors",
        summary["updated"], summary["skipped"], summary["errors"],
    )
    return summary


# ---------------------------------------------------------------------------
# Load helper (used by pharma_agent.py)
# ---------------------------------------------------------------------------

def load_patents(patents_path: Path = PATENTS_PATH) -> list[dict]:
    """Load patents from JSON file. Returns empty list on error."""
    try:
        if patents_path.exists():
            with open(patents_path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.warning("Could not load patents.json: %s", exc)
    return []


def build_patent_index(patents: list[dict]) -> dict[str, list[dict]]:
    """Build search index keyed by drug name, brand, and NCM."""
    index: dict[str, list[dict]] = {}
    for p in patents:
        terms = (
            [p.get("principio_ativo", "").upper(), p.get("marca", "").upper()]
            + [n.upper() for n in p.get("ncms", [])]
            + p.get("principio_ativo", "").upper().split()
        )
        for term in terms:
            if not term:
                continue
            index.setdefault(term, [])
            if p not in index[term]:
                index[term].append(p)
    return index
