"""
Test — PharmaIntel BR Master Orchestrator
Run: python test_master_orchestrator.py
"""
import sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

from src import master_orchestrator, job_manager, quality_agent

REQUEST = (
    "Evaluate Brazil opportunity for trastuzumab API/IFA and finished dosage forms. "
    "Identify ANVISA/CMED/import signals, sourcing route, Brazilian partner categories "
    "and recommended commercial action."
)


def main() -> None:
    job_manager.clear_jobs()
    result = master_orchestrator.run(REQUEST)
    quality = quality_agent.check(result)

    print(f"\nREQUEST: {REQUEST}\n")
    print(f"Molecule:                {result['molecule']}")
    print(f"Therapeutic Area:        {result['therapeutic_area']}")
    print(f"Opportunity Level:       {result['opportunity_level']}")
    print(f"Assigned Agents:         {', '.join(result['assigned_agents'])}")
    print(f"Missing Information:     {result['missing_information']}")
    print(f"Next Action:             {result['next_action']}")
    print(f"Job Status:              {result['job_status']}")
    print(f"Contract Protection Req: {result['contract_protection'].get('warning')}")
    print(f"\nQuality Check Passed:    {quality['passed']}")
    for issue in quality["issues"]:
        print(f"  WARN: {issue}")

    assert result["molecule"] == "trastuzumab", f"Expected molecule trastuzumab, got {result['molecule']!r}"
    assert result["therapeutic_area"] == "oncology", f"Expected oncology, got {result['therapeutic_area']!r}"
    assert "HIGH" in (result["opportunity_level"] or ""), f"Expected HIGH opportunity, got {result['opportunity_level']!r}"
    assert result["next_action"]["type"] == "commercial", f"Expected commercial next action, got {result['next_action']!r}"
    assert result["contract_protection"].get("warning") is True, "Expected contract protection to be required"
    assert "therapeutic area not specified" not in result["missing_information"]
    assert quality["passed"], f"Quality agent flagged issues: {quality['issues']}"

    print("\nALL ASSERTIONS PASSED.")


if __name__ == "__main__":
    main()
