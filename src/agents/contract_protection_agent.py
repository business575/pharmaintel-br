"""Contract Protection Agent — warns before introducing parties. Recommends legal protection."""
from __future__ import annotations

CHECKLIST = {
    "NDA":               "Non-Disclosure Agreement — required before sharing company names, contacts or commercial data",
    "Non-circumvention": "Non-circumvention clause — prevents parties from bypassing PharmaIntel BR after introduction",
    "Success fee":       "Success fee agreement — defines PharmaIntel BR commission on closed agreements (3–5%)",
    "Account ownership": "Account ownership clause — ensures PharmaIntel BR retains the commercial relationship",
    "Renewal commission":"Renewal commission — commission applies to contract renewals, not only first transaction",
    "Payment trigger":   "Payment trigger — defines when success fee is due (LOI, contract signature, first payment)",
}

HIGH_RISK = ("brazil_market_entry", "api_ifa_sourcing", "commercial_proposal", "partner_mapping")


def run(intake: dict, scoring: dict) -> dict:
    rtype = intake.get("request_type", "")
    level = scoring.get("level", "")

    if rtype not in HIGH_RISK and level not in ("HIGH OPPORTUNITY", "MEDIUM OPPORTUNITY"):
        return {"warning": False, "message": "No immediate protection risk identified at this stage.", "checklist": []}

    if rtype in ("brazil_market_entry", "api_ifa_sourcing", "commercial_proposal"):
        required = ["NDA", "Non-circumvention", "Success fee", "Payment trigger"]
        optional = ["Account ownership", "Renewal commission"]
    else:
        required = ["NDA", "Non-circumvention"]
        optional = ["Success fee", "Payment trigger"]

    return {
        "warning":  True,
        "message":  "⚠  PROTECTION REQUIRED before sharing partner, buyer or supplier information.",
        "required": {k: CHECKLIST[k] for k in required},
        "optional": {k: CHECKLIST[k] for k in optional},
        "action":   "Send NDA and non-circumvention agreement before proceeding to introduction.",
        "note":     "All introductions on IFA Partner BR are NDA-gated by default. Do not share direct contacts before NDA is signed.",
    }
