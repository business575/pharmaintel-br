"""Proposal Agent — creates commercial proposals. Does NOT force pricing on intelligence-only requests."""
from __future__ import annotations

SERVICES_BR   = {"Molecule Sourcing Diagnosis": "R$ 2.500 – R$ 5.000", "International Supplier Mapping": "R$ 7.500 – R$ 15.000", "Strategic Sourcing Report": "R$ 10.000 – R$ 20.000", "Success Fee": "3% – 5% on closed agreements"}
SERVICES_INTL = {"Supplier Listing (12 months)": "USD 500 – USD 1.500", "Brazil Market Entry Report": "USD 1.500 – USD 3.000", "Local Representation": "USD 3.500+/month", "Success Fee": "3% – 5% on closed agreements"}
PRICING_NOTE  = "Pricing may vary depending on molecule complexity, data availability, regulatory status and required level of business development support."


def run(intake: dict, scoring: dict) -> dict:
    rtype       = intake.get("request_type", "")
    molecule    = intake.get("molecule", "molecule")
    level       = scoring.get("level", "REQUIRES VALIDATION")
    country     = (intake.get("country") or "").lower()
    is_intl     = rtype in ("brazil_market_entry", "api_ifa_sourcing") or (country and country != "brazil")

    if is_intl:
        svc, price, services, audience = "Brazil Market Entry Report", SERVICES_INTL["Brazil Market Entry Report"], SERVICES_INTL, "International Supplier"
        rationale = f"Based on {level} for {molecule} in Brazil, a Brazil Market Entry Report provides molecule-level ANVISA/CMED/import intelligence and a qualified Brazilian partner map."
    else:
        svc, price, services, audience = "Molecule Sourcing Diagnosis", SERVICES_BR["Molecule Sourcing Diagnosis"], SERVICES_BR, "Brazilian Pharma Company"
        rationale = f"Based on {level} for {molecule} in Brazil, a Molecule Sourcing Diagnosis will identify qualified international suppliers and map the commercial sourcing route."

    return {
        "audience": audience, "recommended_service": svc, "recommended_price": price,
        "rationale": rationale, "full_service_list": services, "pricing_note": PRICING_NOTE,
        "contact": "business@globalhealthcareaccess.com",
        "book_call": "https://calendly.com/vinicius-hospitalar/30min",
        "platform":  "https://pharmaintel-br.onrender.com/?page=partnership",
        "evidence":  "INDICATIVE",
    }
