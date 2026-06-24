"""
PharmaIntel BR — Agent Orchestrator
Coordinates specialized agents for pharmaceutical market intelligence,
API/IFA sourcing, CDMO opportunities and Brazil market-entry analysis.

Usage:
    from src.orchestrator import run_orchestrator, print_result
    result = run_orchestrator("Evaluate Brazil opportunity for trastuzumab API/IFA")
    print_result(result)
"""
from __future__ import annotations

from src.agents import intake_agent
from src.agents import regulatory_agent
from src.agents import cmed_pricing_agent
from src.agents import import_intelligence_agent
from src.agents import sourcing_agent
from src.agents import partner_mapping_agent
from src.agents import opportunity_scoring_agent
from src.agents import commercial_report_agent
from src.agents import proposal_agent
from src.agents import followup_agent
from src.agents import contract_protection_agent


def run_orchestrator(request: str) -> dict:
    intake      = intake_agent.run(request)
    regulatory  = regulatory_agent.run(intake)
    cmed        = cmed_pricing_agent.run(intake)
    import_intel= import_intelligence_agent.run(intake)
    sourcing    = sourcing_agent.run(intake, regulatory)
    partner     = partner_mapping_agent.run(intake, regulatory)
    scoring     = opportunity_scoring_agent.run(intake, regulatory, import_intel, partner)
    report      = commercial_report_agent.run(intake, regulatory, cmed, import_intel, sourcing, partner, scoring)
    proposal    = proposal_agent.run(intake, scoring)
    followup    = followup_agent.run(intake, scoring)
    protection  = contract_protection_agent.run(intake, scoring)

    return {
        "intake": intake, "regulatory": regulatory, "cmed": cmed,
        "import": import_intel, "sourcing": sourcing, "partner": partner,
        "scoring": scoring, "report": report, "proposal": proposal,
        "followup": followup, "protection": protection,
    }


def print_result(result: dict) -> None:
    print(result["report"]["report"])

    p = result["proposal"]
    print(f"\n{'─'*60}\nCOMMERCIAL PROPOSAL\n{'─'*60}")
    print(f"Audience:  {p['audience']}")
    print(f"Service:   {p['recommended_service']} — {p['recommended_price']}")
    print(f"Rationale: {p['rationale']}")
    print(f"Note:      {p['pricing_note']}")

    f = result["followup"]
    print(f"\n{'─'*60}\nNEXT ACTION [{f['priority']}]\n{'─'*60}")
    print(f"Action: {f['next_action']}")
    print(f"Reason: {f['reason']}")
    if "cta" in f:
        print(f"CTA:    {f['cta']}")

    prot = result["protection"]
    if prot.get("warning"):
        print(f"\n{'─'*60}\n⚠  CONTRACT PROTECTION\n{'─'*60}")
        print(prot["message"])
        print(f"Action: {prot['action']}")
        for k, v in prot.get("required", {}).items():
            print(f"  [REQUIRED] {k}: {v}")
        for k, v in prot.get("optional", {}).items():
            print(f"  [OPTIONAL] {k}: {v}")
