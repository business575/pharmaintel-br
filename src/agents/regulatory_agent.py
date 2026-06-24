"""
Regulatory Agent — ANVISA registration data lookup.
Does NOT invent data. Labels everything appropriately.
"""
from __future__ import annotations

KNOWN_REGISTRATIONS: dict[str, dict] = {
    "trastuzumab": {
        "status":       "Active registrations exist in Brazil",
        "holders":      ["Roche", "Biocon (biosimilar)", "Samsung Bioepis (biosimilar)"],
        "dosage_forms": ["Lyophilized powder 150mg", "Concentrate 600mg/5ml"],
        "category":     "Biological — monoclonal antibody",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "bevacizumab": {
        "status":       "Active registrations exist in Brazil",
        "holders":      ["Roche", "Pfizer (biosimilar)"],
        "dosage_forms": ["Concentrate for solution 25mg/ml"],
        "category":     "Biological — monoclonal antibody",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "rituximab": {
        "status":       "Active registrations exist in Brazil",
        "holders":      ["Roche", "Libbs (biosimilar)"],
        "dosage_forms": ["Concentrate for solution 10mg/ml"],
        "category":     "Biological — monoclonal antibody",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "pembrolizumab": {
        "status":       "Active registration exists in Brazil",
        "holders":      ["MSD (Merck)"],
        "dosage_forms": ["Concentrate for solution 25mg/ml"],
        "category":     "Biological — monoclonal antibody (checkpoint inhibitor)",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "imatinib": {
        "status":       "Multiple active registrations",
        "holders":      ["Novartis", "EMS", "Eurofarma", "União Química", "Cristália", "Libbs"],
        "dosage_forms": ["Tablet 100mg", "Tablet 400mg", "Capsule 100mg"],
        "category":     "Small molecule — tyrosine kinase inhibitor",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "paclitaxel": {
        "status":       "Multiple active registrations",
        "holders":      ["Zodiac", "Blau", "Eurofarma", "Bergamo"],
        "dosage_forms": ["Concentrate for solution 6mg/ml"],
        "category":     "Small molecule — taxane",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "albumin": {
        "status":       "Active registrations exist",
        "holders":      ["CSL Behring", "Grifols", "Octapharma", "Instituto Butantan"],
        "dosage_forms": ["Solution 4%", "Solution 20%", "Solution 25%"],
        "category":     "Plasma-derived biological",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "immunoglobulin": {
        "status":       "Active registrations exist",
        "holders":      ["CSL Behring", "Grifols", "Octapharma", "Kedrion"],
        "dosage_forms": ["IV solution 50mg/ml", "IV solution 100mg/ml", "Subcutaneous solution"],
        "category":     "Plasma-derived biological",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "semaglutide": {
        "status":       "Active registration exists in Brazil",
        "holders":      ["Novo Nordisk"],
        "dosage_forms": ["Solution for injection 0.25mg/0.5ml", "1mg/0.5ml", "Oral tablet 3/7/14mg"],
        "category":     "GLP-1 receptor agonist — biological peptide",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "adalimumab": {
        "status":       "Active registrations exist",
        "holders":      ["AbbVie", "Eurofarma (biosimilar)", "Cristália (biosimilar)"],
        "dosage_forms": ["Solution for injection 40mg/0.8ml"],
        "category":     "Biological — monoclonal antibody (anti-TNF)",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "tacrolimus": {
        "status":       "Multiple active registrations",
        "holders":      ["Astellas", "Eurofarma", "EMS", "Libbs"],
        "dosage_forms": ["Capsule 0.5mg", "1mg", "5mg", "Extended release"],
        "category":     "Small molecule — calcineurin inhibitor",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
    "levetiracetam": {
        "status":       "Multiple active registrations",
        "holders":      ["UCB", "EMS", "Eurofarma", "União Química", "Cristália"],
        "dosage_forms": ["Tablet 250mg/500mg/750mg/1000mg", "Solution for infusion"],
        "category":     "Small molecule — antiepileptic",
        "source":       "Curated from ANVISA public registry — not dynamically loaded",
        "evidence":     "INDICATIVE",
    },
}


def run(intake: dict) -> dict:
    molecule = intake.get("molecule")

    if not molecule:
        return {
            "found":    False,
            "message":  "No molecule identified. Specify active ingredient for ANVISA lookup.",
            "evidence": "REQUIRES VALIDATION",
            "data":     {},
        }

    data = KNOWN_REGISTRATIONS.get(molecule)
    if data:
        return {
            "found":    True,
            "molecule": molecule,
            "data":     data,
            "evidence": data.get("evidence", "INDICATIVE"),
            "note":     "Data based on curated public ANVISA registry. Verify current status at consultas.anvisa.gov.br before commercial use.",
        }

    return {
        "found":    False,
        "molecule": molecule,
        "message":  f"No curated ANVISA data for '{molecule}'. Active validation required via consultas.anvisa.gov.br.",
        "evidence": "REQUIRES VALIDATION",
        "data":     {},
        "note":     "Run ANVISA ETL or query consultas.anvisa.gov.br directly.",
    }
