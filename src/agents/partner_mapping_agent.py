"""
Partner Mapping Agent — maps Brazilian partner categories.
Does NOT invent direct contacts. Categories only.
"""
from __future__ import annotations

PARTNER_CATEGORIES: dict[str, dict] = {
    "oncology": {
        "buyers": ["Brazilian oncology hospital pharmacy networks (A.C. Camargo, Albert Einstein, Sírio-Libanês, Beneficência Portuguesa)", "SUS oncology centers — CACON and UNACON network", "Brazilian oncology product distributors", "ANVISA registration holders for oncology molecules"],
        "registration_holders": ["Eurofarma", "EMS", "União Química", "Cristália", "Libbs", "Blau", "Zodiac", "Bergamo"],
    },
    "plasma_derived": {
        "buyers": ["Brazilian hospital pharmacy networks — ICU and transplant centers", "SUS plasma-derived product procurement (CONASS/CONASEMS)", "Brazilian biologics importers and distributors", "ANVISA registration holders for albumin and IVIG"],
        "registration_holders": ["CSL Behring Brasil", "Grifols Brasil", "Octapharma", "Instituto Butantan"],
    },
    "immunology": {
        "buyers": ["Transplant center pharmacy networks", "Autoimmune disease specialty clinics", "Brazilian immunology product distributors"],
        "registration_holders": ["Astellas", "Eurofarma", "EMS", "Libbs", "Cristália"],
    },
    "cns": {
        "buyers": ["Brazilian neurology and psychiatry clinic networks", "SUS mental health and neurology protocol buyers", "Hospital pharmacy networks — epilepsy and CNS protocols"],
        "registration_holders": ["EMS", "Eurofarma", "UCB do Brasil", "União Química", "Cristália", "Libbs"],
    },
    "rare_diseases": {
        "buyers": ["Brazilian rare disease patient associations (Aliança Brasileira de Doenças Raras)", "SUS rare disease program procurement", "Specialty distributors for orphan drugs"],
        "registration_holders": ["Sanofi Genzyme Brasil", "Takeda Brasil", "BioMarin", "Ultragenyx"],
    },
    "glp1_metabolic": {
        "buyers": ["Brazilian endocrinology clinic networks", "Pharmacy chains — retail and specialty", "Private health plans — obesity protocol purchasers"],
        "registration_holders": ["Novo Nordisk Brasil", "Eli Lilly Brasil"],
    },
}

DEFAULT: dict = {
    "buyers": ["Brazilian pharmaceutical importers and distributors", "ANVISA registration holders for target molecule", "Brazilian hospital pharmacy networks", "Brazilian generic pharmaceutical companies"],
    "registration_holders": ["EMS", "Eurofarma", "Blau", "União Química", "Cristália", "Libbs", "Hypera Pharma"],
}


def run(intake: dict, regulatory: dict) -> dict:
    area = intake.get("area")
    cats = PARTNER_CATEGORIES.get(area, DEFAULT)
    reg_holders = (regulatory.get("data") or {}).get("holders", []) if regulatory.get("found") else []
    return {
        "molecule":          intake.get("molecule"),
        "area":              area,
        "buyer_categories":  cats["buyers"],
        "known_reg_holders": reg_holders or cats["registration_holders"],
        "validation_note":   "Potential target category — requires validation. No direct contacts confirmed. All introductions must be structured under NDA.",
        "evidence":          "INDICATIVE",
    }
