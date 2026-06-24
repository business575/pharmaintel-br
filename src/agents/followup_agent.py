"""Follow-up Agent — always returns one clear next action."""
from __future__ import annotations

ACTIONS = {
    "api_ifa_sourcing":            "Request molecule list and GMP certifications from potential supplier",
    "fdf_opportunity":             "Request FDF portfolio, dosage forms and target markets from supplier",
    "cdmo_opportunity":            "Request CDMO capacity, GMP status and available technology transfer terms",
    "brazil_market_entry":         "Schedule 20-minute call to review Brazil buyer match report",
    "molecule_opportunity_report": "Request Molecule Sourcing Diagnosis to identify active suppliers",
    "anvisa_cmed_lookup":          "Verify ANVISA registration status at consultas.anvisa.gov.br",
    "import_intelligence":         "Run Comex Stat ETL to obtain current NCM import data",
    "partner_mapping":             "Qualify top 3 Brazilian registration holders before introduction",
    "commercial_proposal":         "Send proposal and request NDA before sharing partner data",
}

MISSING_ACTIONS = {
    "molecule/active ingredient not specified": "Request molecule or active ingredient specification",
    "therapeutic area not specified":           "Request therapeutic area or product category",
    "supplier country not specified":           "Request supplier country and GMP certification status",
}


def run(intake: dict, scoring: dict) -> dict:
    for m in intake.get("missing", []):
        if m in MISSING_ACTIONS:
            return {"next_action": MISSING_ACTIONS[m], "reason": f"Missing info blocking analysis: {m}", "priority": "HIGH"}

    action = ACTIONS.get(intake.get("request_type", ""), "Schedule 20-minute call to review opportunity")
    level  = scoring.get("level", "")
    prio   = "HIGH" if level == "HIGH OPPORTUNITY" else "MEDIUM"
    cta    = "https://calendly.com/vinicius-hospitalar/30min" if prio == "HIGH" else "business@globalhealthcareaccess.com"

    return {"next_action": action, "reason": f"Standard next step at {level}.", "priority": prio, "cta": cta}
