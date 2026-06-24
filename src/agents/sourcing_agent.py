"""
Sourcing Agent — suggests sourcing routes.
Does NOT invent supplier names, contacts or websites.
"""
from __future__ import annotations

NO_SUPPLIER_MESSAGE = (
    "No verified supplier listed yet for this molecule. "
    "Active sourcing is required. "
    "PharmaIntel BR can execute active international sourcing — "
    "see Molecule Sourcing Diagnosis or Strategic Sourcing Report services."
)

BASE_ROUTES: dict[str, list[str]] = {
    "api_ifa_sourcing":            ["Identify API manufacturers with ANVISA GMP or DMF Brazil approval", "Map CEP (Certificate of Suitability) holders for target molecule", "Evaluate WHO-GMP certified API manufacturers", "Check US FDA / EMA approved API manufacturers for dual-market supply"],
    "fdf_opportunity":             ["Map FDF manufacturers with ANVISA registration or GMP certification", "Identify WHO-GMP certified finished dosage form manufacturers", "Evaluate technology transfer opportunities from originator or generic holders", "Consider local Brazilian fill-finish CDMOs for imported API"],
    "cdmo_opportunity":            ["Map Brazilian CDMOs with capacity for target dosage form", "Identify Indian CDMOs with ANVISA GMP or export certification to Brazil", "Evaluate fill-finish partners for injectable or biologics", "Consider technology transfer + local CDMO hybrid model"],
    "brazil_market_entry":         ["Register on IFA Partner BR for NDA-gated buyer introductions", "Obtain ANVISA GMP certification for Brazilian market access", "Identify Brazilian importer/distributor with active ANVISA registration", "Appoint local regulatory representative for ANVISA submission support"],
    "molecule_opportunity_report": ["Evaluate API/IFA supply route for target molecule", "Map Brazilian ANVISA registration holders as potential buyers", "Identify finished dosage form sourcing options", "Assess CDMO capacity for local production"],
}

AREA_ROUTES: dict[str, list[str]] = {
    "plasma_derived": ["Source HSA or IVIG from WHO-GMP certified plasma fractionators", "Evaluate Indian plasma-derived manufacturers with international GMP", "Map Brazilian hospital pharmacy networks as buyers for plasma-derived products"],
    "oncology":       ["Prioritize ANVISA GMP or US FDA approved API manufacturers for oncology", "Map Brazilian oncology hospital pharmacy networks as end buyers", "Evaluate biosimilar development if originator patent has expired"],
    "cns":            ["Identify Indian generic API manufacturers for CNS molecules with WHO-GMP", "Map Brazilian neurology/psychiatry clinic networks as buyers"],
    "immunology":     ["Identify calcineurin inhibitor or immunosuppressant API suppliers with ANVISA GMP", "Map Brazilian transplant center pharmacy networks"],
    "rare_diseases":  ["Identify manufacturers with orphan drug or rare disease product portfolio", "Map SUS rare disease program procurement as primary buyer route"],
}


def run(intake: dict, regulatory: dict) -> dict:
    request_type = intake.get("request_type", "molecule_opportunity_report")
    area         = intake.get("area")
    routes       = BASE_ROUTES.get(request_type, BASE_ROUTES["molecule_opportunity_report"])
    area_routes  = AREA_ROUTES.get(area, [])
    return {
        "molecule":      intake.get("molecule"),
        "request_type":  request_type,
        "routes":        routes + area_routes,
        "supplier_note": NO_SUPPLIER_MESSAGE,
        "evidence":      "INDICATIVE",
        "note":          "Sourcing routes are strategic recommendations. Active sourcing and supplier validation required before commercial engagement.",
    }
