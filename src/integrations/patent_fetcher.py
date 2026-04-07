"""
patent_fetcher.py
=================
PharmaIntel BR — Atualização automática de patentes farmacêuticas.

Fontes (sem necessidade de API key):
    1. Inferência automática por data — sempre funciona
    2. INPI pePI — scraping do portal público brasileiro
       https://busca.inpi.gov.br/pePI/
    3. Espacenet (EPO) — scraping do portal público europeu
       https://worldwide.espacenet.com/
    4. Google Patents — fallback público
       https://patents.google.com/

Uso:
    from src.integrations.patent_fetcher import refresh_patents
    result = refresh_patents()  # atualiza data/patents.json
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

PATENTS_PATH = Path(__file__).resolve().parents[2] / "data" / "patents.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.verify = False


# ---------------------------------------------------------------------------
# 1. Status inference (no network — always works)
# ---------------------------------------------------------------------------

def _infer_status(exp_br: str) -> str:
    """Infer patent status from expiration date string (ISO format)."""
    if not exp_br:
        return ""
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
        return ""


def _infer_opportunity(status: str, exp_br: str, current_opp: str) -> str:
    """Update biosimilar opportunity label based on current status."""
    if status == "Expirada" and "IMEDIATA" not in (current_opp or ""):
        return f"IMEDIATA — patente expirou em {exp_br} no Brasil"
    return current_opp


# ---------------------------------------------------------------------------
# 2. INPI pePI scraper
# ---------------------------------------------------------------------------

INPI_BASE = "https://busca.inpi.gov.br/pePI/servlet/PatenteServlet"
INPI_SEARCH = "https://busca.inpi.gov.br/pePI/servlet/PatenteServlet?Action=pesquisaBasica"


def _inpi_search_by_pi(pi_number: str) -> Optional[dict]:
    """Query INPI pePI by PI/MU number. Returns status and dates found."""
    if not pi_number:
        return None
    try:
        resp = SESSION.get(
            INPI_BASE,
            params={"Action": "detail", "CodPedido": pi_number},
            timeout=20,
        )
        if resp.status_code != 200:
            return None

        text = resp.text
        result: dict = {"pi_number": pi_number, "source": "inpi"}

        # Situação (status)
        m = re.search(
            r"Situa[çc][aã]o[^<]*<[^>]+>\s*([^<]{3,60})<",
            text, re.IGNORECASE,
        )
        if m:
            result["situacao_inpi"] = m.group(1).strip()

        # Dates dd/mm/yyyy
        dates_found = re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", text)
        if dates_found:
            result["datas_encontradas"] = list(dict.fromkeys(dates_found))  # unique, ordered

            # Try to find expiry: look for "vigência" label near a date
            vig = re.search(
                r"vig[eê]ncia[^<]*<[^>]+>\s*(\d{2}/\d{2}/\d{4})",
                text, re.IGNORECASE,
            )
            if vig:
                d, m2, y = vig.group(1).split("/")
                result["expiracao_inpi"] = f"{y}-{m2}-{d}"

        return result if len(result) > 2 else None

    except Exception as exc:
        logger.debug("INPI scrape error (%s): %s", pi_number, exc)
        return None


def _inpi_search_by_name(drug_name: str) -> Optional[dict]:
    """Search INPI pePI by drug INN name. Returns first relevant result."""
    try:
        resp = SESSION.post(
            INPI_SEARCH,
            data={
                "Action": "pesquisaBasica",
                "txtTexto": drug_name,
                "tipoBusca": "BI",  # busca por INN/denominação
                "txtNumProcesso": "",
            },
            timeout=20,
        )
        if resp.status_code != 200:
            return None

        text = resp.text
        # Extract first PI number from results table
        pi_match = re.search(r"(PI\s*\d{7}[\s\-]\d)", text, re.IGNORECASE)
        if pi_match:
            pi_num = re.sub(r"\s", "", pi_match.group(1))
            return {"pi_found": pi_num, "source": "inpi_search"}

        # Also look for MU (model of utility)
        mu_match = re.search(r"(MU\s*\d{7}[\s\-]\d)", text, re.IGNORECASE)
        if mu_match:
            return {"pi_found": re.sub(r"\s", "", mu_match.group(1)), "source": "inpi_search"}

        return None
    except Exception as exc:
        logger.debug("INPI name search error (%s): %s", drug_name, exc)
        return None


# ---------------------------------------------------------------------------
# 3. Espacenet (EPO) scraper
# ---------------------------------------------------------------------------

ESPACENET_URL = "https://worldwide.espacenet.com/patent/search/family/{ep_number}/legal"
ESPACENET_BIBLIO = "https://worldwide.espacenet.com/patent/search?q=pn%3D{ep_number}"
ESPACENET_OPS_JSON = "https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{ep_number}/biblio.json"


def _espacenet_fetch(ep_number: str) -> Optional[dict]:
    """
    Scrape Espacenet public portal for a patent.
    Tries JSON endpoint first (no auth needed for basic data), then HTML.
    """
    if not ep_number:
        return None

    ep_clean = re.sub(r"[^A-Z0-9]", "", ep_number.upper())

    # Try Espacenet search page
    try:
        url = f"https://worldwide.espacenet.com/patent/search?q=pn%3D{ep_clean}"
        resp = SESSION.get(url, timeout=20)
        if resp.status_code == 200:
            text = resp.text
            result: dict = {"ep_number": ep_number, "source": "espacenet"}

            # Look for expiry / lapse dates in the HTML
            # Espacenet shows legal events like "LAPSE" with dates
            lapse = re.findall(
                r"(LAPSE|CEASED|EXPIRED|REVOKED)[^<]*(\d{4}-\d{2}-\d{2}|\d{8})",
                text, re.IGNORECASE,
            )
            if lapse:
                raw_date = lapse[0][1]
                if len(raw_date) == 8:
                    raw_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                result["expiracao_ep"] = raw_date
                result["evento_legal"] = lapse[0][0].capitalize()
                return result

            # Priority date (to estimate 20-year term)
            prio = re.search(
                r"priority[^<]*(\d{4}-\d{2}-\d{2}|\d{8})",
                text, re.IGNORECASE,
            )
            if prio:
                raw_date = prio.group(1)
                if len(raw_date) == 8:
                    raw_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                try:
                    pdt = date.fromisoformat(raw_date)
                    result["data_prioridade"] = raw_date
                    result["expiracao_estimada"] = f"{pdt.year + 20}-{raw_date[5:]}"
                except ValueError:
                    pass
                return result if len(result) > 2 else None

    except Exception as exc:
        logger.debug("Espacenet fetch error (%s): %s", ep_number, exc)

    return None


# ---------------------------------------------------------------------------
# 4. Google Patents scraper
# ---------------------------------------------------------------------------

def _google_patents_fetch(ep_number: str, drug_name: str) -> Optional[dict]:
    """Scrape Google Patents for a patent status."""
    ep_clean = re.sub(r"[^A-Z0-9]", "", ep_number.upper()) if ep_number else ""
    query = ep_clean or drug_name

    if not query:
        return None

    try:
        url = f"https://patents.google.com/patent/{ep_clean}/en" if ep_clean else (
            f"https://patents.google.com/patent/?q={requests.utils.quote(drug_name)}&assignee=&before=priority:20300101"
        )
        resp = SESSION.get(url, timeout=20, allow_redirects=True)
        if resp.status_code != 200:
            return None

        text = resp.text
        result: dict = {"source": "google_patents"}

        # Status badge: "Active", "Expired", "Pending"
        status_m = re.search(
            r'"legal-status"[^>]*>([^<]{3,30})<',
            text, re.IGNORECASE,
        )
        if status_m:
            result["google_status"] = status_m.group(1).strip()

        # Expiry date
        exp_m = re.search(
            r'expir(?:ation|y)[^<"]*?(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})',
            text, re.IGNORECASE,
        )
        if exp_m:
            raw = exp_m.group(1)
            if "/" in raw:
                parts = raw.split("/")
                raw = f"{parts[2]}-{parts[1]}-{parts[0]}"
            result["expiracao_google"] = raw

        # Priority date
        prio_m = re.search(
            r'"priority[- ]date"[^>]*>([^<]{6,20})<',
            text, re.IGNORECASE,
        )
        if prio_m:
            result["prioridade_google"] = prio_m.group(1).strip()

        return result if len(result) > 1 else None

    except Exception as exc:
        logger.debug("Google Patents error (%s): %s", query, exc)
        return None


# ---------------------------------------------------------------------------
# Main refresh
# ---------------------------------------------------------------------------

def refresh_patents(
    patents_path: Path = PATENTS_PATH,
    delay_s: float = 2.0,
    use_inpi: bool = True,
    use_espacenet: bool = True,
    use_google: bool = True,
) -> dict:
    """
    Refresh patent data from public sources (no API keys needed).

    Strategy (in order):
        1. Auto-infer status from stored expiration date (instant)
        2. INPI pePI scraping — for PI numbers (Brazilian patent office)
        3. Espacenet scraping — for EP numbers (European patents)
        4. Google Patents — fallback for any patent

    Reads patents.json, updates status/dates, writes back to disk.

    Returns:
        Summary dict: {updated, skipped, errors, total}
    """
    if not patents_path.exists():
        logger.error("patents.json not found: %s", patents_path)
        return {"error": "patents.json not found", "updated": 0}

    with open(patents_path, encoding="utf-8") as f:
        patents: list[dict] = json.load(f)

    summary = {"updated": 0, "skipped": 0, "errors": 0, "total": len(patents)}
    now_iso = date.today().isoformat()

    for patent in patents:
        drug      = patent.get("principio_ativo", "?")
        ep_number = patent.get("ep_number", "")
        inpi_pi   = patent.get("inpi_pi", "")
        changed   = False

        logger.info("Processing: %s", drug)

        # ── Step 1: Status from stored date (always runs, no network) ─────
        new_status = _infer_status(patent.get("patente_expiracao_br", ""))
        if new_status and new_status != patent.get("status", ""):
            logger.info("  %s: status %s → %s", drug, patent.get("status"), new_status)
            patent["status"] = new_status
            changed = True

        new_opp = _infer_opportunity(
            patent.get("status", ""),
            patent.get("patente_expiracao_br", ""),
            patent.get("oportunidade_biossimilar", ""),
        )
        if new_opp != patent.get("oportunidade_biossimilar", ""):
            patent["oportunidade_biossimilar"] = new_opp
            changed = True

        # ── Step 2: INPI (Brazilian patent office) ────────────────────────
        if use_inpi:
            inpi_data = None

            # Try by PI number if we have it
            if inpi_pi:
                inpi_data = _inpi_search_by_pi(inpi_pi)
                time.sleep(delay_s)

            # Try by drug name if no PI found yet
            if not inpi_data and not inpi_pi:
                search = _inpi_search_by_name(drug)
                if search and search.get("pi_found"):
                    patent["inpi_pi"] = search["pi_found"]
                    inpi_data = _inpi_search_by_pi(search["pi_found"])
                    changed = True
                time.sleep(delay_s)

            if inpi_data:
                # Use INPI expiry date if more precise
                inpi_exp = inpi_data.get("expiracao_inpi", "")
                if inpi_exp and not patent.get("patente_expiracao_br"):
                    patent["patente_expiracao_br"] = inpi_exp
                    patent["source"] = "inpi"
                    new_status2 = _infer_status(inpi_exp)
                    if new_status2:
                        patent["status"] = new_status2
                    changed = True

                # Reflect INPI situação
                situacao = inpi_data.get("situacao_inpi", "").lower()
                if any(w in situacao for w in ("arquiv", "extint", "nulo", "cadu")):
                    if patent.get("status") != "Expirada":
                        patent["status"] = "Expirada"
                        patent["source"] = "inpi"
                        changed = True

        # ── Step 3: Espacenet / EPO ───────────────────────────────────────
        if use_espacenet and ep_number:
            try:
                esp_data = _espacenet_fetch(ep_number)
                if esp_data:
                    # If Espacenet reports a lapse/expiry event, trust it
                    if esp_data.get("expiracao_ep"):
                        if not patent.get("patente_expiracao_br"):
                            patent["patente_expiracao_br"] = esp_data["expiracao_ep"]
                            changed = True
                        if not patent.get("patente_expiracao_us"):
                            patent["patente_expiracao_us"] = esp_data["expiracao_ep"]
                            changed = True
                        patent["source"] = "espacenet"

                    # Use estimated from priority if no expiry stored
                    elif esp_data.get("expiracao_estimada") and not patent.get("patente_expiracao_us"):
                        patent["patente_expiracao_us"] = esp_data["expiracao_estimada"]
                        patent["source"] = "espacenet_estimado"
                        changed = True

                time.sleep(delay_s)
            except Exception as exc:
                logger.warning("  Espacenet error (%s): %s", ep_number, exc)
                summary["errors"] += 1

        # ── Step 4: Google Patents (fallback) ─────────────────────────────
        if use_google and not patent.get("patente_expiracao_us"):
            try:
                gp = _google_patents_fetch(ep_number, drug)
                if gp:
                    if gp.get("expiracao_google") and not patent.get("patente_expiracao_us"):
                        patent["patente_expiracao_us"] = gp["expiracao_google"]
                        patent["source"] = "google_patents"
                        changed = True

                    # Sync status from Google if we have nothing else
                    if gp.get("google_status") and not patent.get("status"):
                        gs = gp["google_status"].lower()
                        if "expired" in gs:
                            patent["status"] = "Expirada"
                            changed = True
                        elif "active" in gs:
                            patent["status"] = "Vigente"
                            changed = True

                time.sleep(delay_s)
            except Exception as exc:
                logger.debug("  Google Patents error (%s): %s", drug, exc)

        # ── Finalize ──────────────────────────────────────────────────────
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
# Load / index helpers (used by pharma_agent.py)
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


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = refresh_patents()
    print(json.dumps(result, indent=2, ensure_ascii=False))
