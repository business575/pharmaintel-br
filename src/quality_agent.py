"""
Quality Agent — PharmaIntel BR
Final gate before displaying master_orchestrator output. Does NOT generate or
alter content — it only checks the already-produced consolidated dict for
known integrity violations before it reaches the user.
"""
from __future__ import annotations

import re

OFFICIAL_EMAILS = {"business@globalhealthcareaccess.com"}
OFFICIAL_URLS = {
    "https://calendly.com/vinicius-hospitalar/30min",
    "https://pharmaintel-br.onrender.com/?page=partnership",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+")
# Bare digit runs (NCM codes, FOB USD values) must NOT match — only count it as an
# invented phone number when it carries actual phone formatting (+country or (area)).
PHONE_RE = re.compile(r"\+\d{1,3}[\s.-]\d{2,4}[\s.-]\d{3,5}(?:[\s.-]?\d{0,4})?|\(\d{2,3}\)\s?\d{4,5}[\s.-]?\d{4}")

NCM_DISCLAIMER_MARKER = "does not confirm"
CMED_DISCLAIMER_MARKER = "cmed.anvisa.gov.br"


def check(consolidated: dict) -> dict:
    """Inspect a master_orchestrator() consolidated output. Returns {"passed": bool, "issues": [...]}"""
    issues: list[str] = []

    report_text = consolidated.get("executive_summary") or ""
    report_lower = report_text.lower()

    for email in EMAIL_RE.findall(report_text):
        if email.lower() not in OFFICIAL_EMAILS:
            issues.append(f"Possible invented contact email in report: '{email}'")

    for match in PHONE_RE.findall(report_text):
        issues.append(f"Possible invented contact phone number in report: '{match}'")

    if "ncm" in report_lower and NCM_DISCLAIMER_MARKER not in report_lower:
        issues.append("Missing NCM disclaimer in report despite NCM/import data being referenced.")

    if "cmed" in report_lower and CMED_DISCLAIMER_MARKER not in report_lower:
        issues.append("Missing CMED disclaimer in report despite CMED data being referenced.")

    proposal = consolidated.get("commercial_proposal") or {}
    protection = consolidated.get("contract_protection") or {}

    if proposal and not protection:
        issues.append("Commercial proposal present without a contract protection check.")

    if protection.get("warning") and not protection.get("required"):
        issues.append("Contract protection warning raised without a required-actions checklist.")

    if proposal and not protection.get("warning") and not protection.get("message"):
        issues.append("Commercial proposal present but contract protection gate gave no message before introduction.")

    return {"passed": len(issues) == 0, "issues": issues}
