"""
Import Intelligence Agent — NCM/Comex/MDIC import signals.
Always includes mandatory NCM disclaimer. Does NOT claim molecule-specific revenue.
"""
from __future__ import annotations

NCM_DISCLAIMER = (
    "NCM import data is a broad customs category and does not confirm "
    "molecule-specific revenue. Commercial opportunity requires validation "
    "by product, importer, registration holder, supplier and agreement structure."
)

NCM_DATA: dict[str, dict] = {
    "trastuzumab":   {"ncm": "30021520", "description": "Monoclonal antibodies",                     "fob_usd_2025": "USD 265,792,411 [ESTIMATED — full NCM category]",         "top_origins": ["United States", "Germany", "Switzerland", "India"], "trend": "Growing — biosimilar entry and SUS expansion",           "import_dependence": "Very High"},
    "bevacizumab":   {"ncm": "30021520", "description": "Monoclonal antibodies",                     "fob_usd_2025": "USD 265,792,411 [ESTIMATED — shared NCM]",               "top_origins": ["United States", "Germany", "Switzerland"],          "trend": "Stable — biosimilar competition increasing",             "import_dependence": "High"},
    "rituximab":     {"ncm": "30021520", "description": "Monoclonal antibodies",                     "fob_usd_2025": "USD 265,792,411 [ESTIMATED — shared NCM]",               "top_origins": ["Switzerland", "Germany"],                           "trend": "Stable — domestic biosimilar partially substituting",    "import_dependence": "Medium"},
    "pembrolizumab": {"ncm": "30049069", "description": "Oncology pharmaceuticals — broad category", "fob_usd_2025": "USD 1,647,000,000 [ESTIMATED — full NCM, not molecule]", "top_origins": ["United States", "Ireland", "Germany"],             "trend": "Strong growth — checkpoint inhibitors expanding SUS",    "import_dependence": "Very High"},
    "imatinib":      {"ncm": "30049099", "description": "Other pharmaceutical products",             "fob_usd_2025": "USD 602,000,000 [ESTIMATED — broad NCM]",                "top_origins": ["India", "China", "Switzerland"],                   "trend": "Stable — mature market, generics dominate",             "import_dependence": "Medium"},
    "paclitaxel":    {"ncm": "30049069", "description": "Oncology pharmaceuticals",                  "fob_usd_2025": "USD 1,647,000,000 [ESTIMATED — full NCM]",               "top_origins": ["India", "China", "Germany"],                       "trend": "Stable — Indian API suppliers active",                   "import_dependence": "High"},
    "albumin":       {"ncm": "30021235", "description": "Human albumin",                             "fob_usd_2025": "USD 384,000,000 [ESTIMATED — NCM category]",             "top_origins": ["Germany", "Spain", "Australia", "United States"],  "trend": "Growing — ICU protocol expansion, SUS procurement rise", "import_dependence": "Very High"},
    "immunoglobulin":{"ncm": "30021290", "description": "Immunoglobulins — plasma-derived",         "fob_usd_2025": "USD 180,000,000+ [ESTIMATED — NCM category]",            "top_origins": ["Germany", "Spain", "Italy", "United States"],     "trend": "Strong growth — rare disease mandates + immunodeficiency","import_dependence": "Very High"},
    "semaglutide":   {"ncm": "30043900", "description": "Peptide hormones — GLP-1 class",           "fob_usd_2025": "USD 420,000,000+ [ESTIMATED — high growth NCM]",         "top_origins": ["Denmark", "United States"],                        "trend": "Explosive growth — obesity and diabetes epidemic",       "import_dependence": "Very High"},
    "adalimumab":    {"ncm": "30021590", "description": "Other immunological products — biologics",  "fob_usd_2025": "USD 3,612,818,352 [ESTIMATED — full NCM, not molecule]","top_origins": ["United States", "Germany", "Ireland"],             "trend": "Growing biosimilar competition",                         "import_dependence": "High"},
    "tacrolimus":    {"ncm": "30049099", "description": "Other pharmaceutical products",             "fob_usd_2025": "USD 602,000,000 [ESTIMATED — broad NCM]",                "top_origins": ["India", "Germany", "Japan"],                       "trend": "Stable — transplant programs steady",                    "import_dependence": "High"},
    "levetiracetam": {"ncm": "30049099", "description": "Other pharmaceutical products",             "fob_usd_2025": "USD 602,000,000 [ESTIMATED — broad NCM]",                "top_origins": ["India", "China"],                                  "trend": "Stable — competitive generic market",                    "import_dependence": "Medium"},
}


def run(intake: dict) -> dict:
    molecule = intake.get("molecule")
    if not molecule:
        return {"found": False, "message": "No molecule identified.", "disclaimer": NCM_DISCLAIMER, "evidence": "REQUIRES VALIDATION"}

    data = NCM_DATA.get(molecule)
    if data:
        return {"found": True, "molecule": molecule, "data": {**data, "evidence": "ESTIMATED"}, "disclaimer": NCM_DISCLAIMER, "evidence": "ESTIMATED"}

    return {"found": False, "molecule": molecule, "message": f"No curated NCM data for '{molecule}'. Run Comex Stat ETL or query MDIC.", "disclaimer": NCM_DISCLAIMER, "evidence": "REQUIRES VALIDATION"}
