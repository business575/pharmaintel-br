"""
Master Orchestrator — PharmaIntel BR
Receives a business request, runs it through the existing specialized-agent
orchestrator (src.orchestrator.run_orchestrator), tracks the work as a job via
job_manager, and consolidates everything into one structured commercial-decision
output.

Does NOT duplicate agent logic. It only routes, records and consolidates output
already produced by the existing agents.
"""
from __future__ import annotations

from src.orchestrator import run_orchestrator
from src import job_manager

# Which existing agents are relevant to display per request type.
# This does not change what run_orchestrator executes — it only labels, for the
# job record, which agents' output actually matters for this kind of request.
AGENTS_BY_REQUEST_TYPE: dict[str, list[str]] = {
    "api_ifa_sourcing": [
        "intake_agent", "regulatory_agent", "import_intelligence_agent",
        "sourcing_agent", "opportunity_scoring_agent", "proposal_agent",
        "contract_protection_agent",
    ],
    "fdf_opportunity": [
        "intake_agent", "regulatory_agent", "import_intelligence_agent",
        "sourcing_agent", "opportunity_scoring_agent", "proposal_agent",
        "contract_protection_agent",
    ],
    "cdmo_opportunity": [
        "intake_agent", "regulatory_agent", "sourcing_agent",
        "opportunity_scoring_agent", "proposal_agent", "contract_protection_agent",
    ],
    "brazil_market_entry": [
        "intake_agent", "regulatory_agent", "cmed_pricing_agent",
        "import_intelligence_agent", "partner_mapping_agent",
        "opportunity_scoring_agent", "proposal_agent", "contract_protection_agent",
    ],
    "molecule_opportunity_report": [
        "intake_agent", "regulatory_agent", "cmed_pricing_agent",
        "import_intelligence_agent", "sourcing_agent", "partner_mapping_agent",
        "opportunity_scoring_agent", "commercial_report_agent", "followup_agent",
    ],
    "anvisa_cmed_lookup": ["intake_agent", "regulatory_agent", "cmed_pricing_agent"],
    "import_intelligence": ["intake_agent", "import_intelligence_agent"],
    "partner_mapping": [
        "intake_agent", "regulatory_agent", "partner_mapping_agent",
        "contract_protection_agent",
    ],
    "commercial_proposal": [
        "intake_agent", "opportunity_scoring_agent", "proposal_agent",
        "contract_protection_agent",
    ],
}

DEFAULT_AGENTS = [
    "intake_agent", "regulatory_agent", "cmed_pricing_agent",
    "import_intelligence_agent", "sourcing_agent", "partner_mapping_agent",
    "opportunity_scoring_agent", "commercial_report_agent", "proposal_agent",
    "followup_agent", "contract_protection_agent",
]


def _assign_agents(request_type: str) -> list[str]:
    return AGENTS_BY_REQUEST_TYPE.get(request_type, DEFAULT_AGENTS)


def _job_priority(level: str, urgency: str) -> str:
    if level == "HIGH OPPORTUNITY" or urgency == "high":
        return "HIGH"
    if level == "MEDIUM OPPORTUNITY":
        return "MEDIUM"
    return "LOW"


def run(request: str) -> dict:
    """Run a business request end-to-end. Returns a consolidated commercial decision dict."""
    result = run_orchestrator(request)

    intake = result["intake"]
    scoring = result["scoring"]
    report = result["report"]
    proposal = result["proposal"]
    followup = result["followup"]
    protection = result["protection"]

    missing = intake.get("missing", [])
    request_type = intake.get("request_type", "molecule_opportunity_report")
    assigned_agents = _assign_agents(request_type)
    priority = _job_priority(scoring.get("level", ""), intake.get("urgency", "medium"))
    status = "blocked" if missing else "completed"

    job = job_manager.create_job(
        title=f"{request_type} — {intake.get('molecule') or 'unspecified molecule'}",
        request=request,
        job_type=request_type,
        priority=priority,
        commercial_value=scoring.get("level"),
        contract_protection_required=bool(protection.get("warning")),
    )
    job_manager.update_job(
        job["job_id"],
        status=status,
        assigned_agents=assigned_agents,
        missing_information=missing,
        next_action=followup.get("next_action"),
    )

    return {
        "executive_summary": report.get("report"),
        "molecule": intake.get("molecule"),
        "therapeutic_area": intake.get("area"),
        "opportunity_level": scoring.get("level"),
        "assigned_agents": assigned_agents,
        "missing_information": missing,
        "commercial_proposal": proposal,
        "contract_protection": protection,
        "next_action": {
            "action": followup.get("next_action"),
            "reason": followup.get("reason"),
            "priority": followup.get("priority"),
            "type": "blocked" if missing else "commercial",
        },
        "job_status": status,
        "job_id": job["job_id"],
    }
