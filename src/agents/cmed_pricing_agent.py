"""
CMED Pricing Agent — Reference prices. Does NOT invent prices.
All prices labeled [INDICATIVE] — verify at cmed.anvisa.gov.br.
"""
from __future__ import annotations

CMED_DATA: dict[str, dict] = {
    "trastuzumab":   {"product": "Trastuzumabe 150mg pó liofilizado", "company": "Roche",           "pf_sem_imp": "R$ 8.747,90"},
    "bevacizumab":   {"product": "Bevacizumabe 400mg/16ml",           "company": "Roche",           "pf_sem_imp": "R$ 3.458,15"},
    "rituximab":     {"product": "Rituximabe 500mg/50ml",             "company": "Roche",           "pf_sem_imp": "R$ 6.512,84"},
    "pembrolizumab": {"product": "Pembrolizumabe 25mg/ml",            "company": "MSD",             "pf_sem_imp": "R$ 33.962,44"},
    "imatinib":      {"product": "Imatinibe 400mg comprimido",        "company": "Ref: Novartis",   "pf_sem_imp": "R$ 312,50"},
    "paclitaxel":    {"product": "Paclitaxel 6mg/ml",                 "company": "Various",         "pf_sem_imp": "R$ 180,00 (indicative range)"},
    "semaglutide":   {"product": "Semaglutida injetável / oral",      "company": "Novo Nordisk",    "pf_sem_imp": "R$ 850,00 – R$ 1.200,00 (range)"},
    "adalimumab":    {"product": "Adalimumabe 40mg/0.8ml",            "company": "AbbVie (Humira)", "pf_sem_imp": "R$ 4.120,00"},
    "albumin":       {"product": "Albumina Humana 20% 50ml",          "company": "CSL/Grifols/Octa","pf_sem_imp": "R$ 180,00 – R$ 320,00 (range)"},
    "immunoglobulin":{"product": "Imunoglobulina Humana IV 5g",       "company": "CSL/Grifols/Kedrion","pf_sem_imp": "R$ 1.200,00 – R$ 2.800,00 (range)"},
    "tacrolimus":    {"product": "Tacrolimo 1mg cápsula",             "company": "Astellas + generics","pf_sem_imp": "R$ 18,00 – R$ 45,00 (range)"},
    "levetiracetam": {"product": "Levetiracetam 500mg comprimido",    "company": "UCB + generics",  "pf_sem_imp": "R$ 8,00 – R$ 22,00 (range)"},
}

DISCLAIMER = "CMED prices are reference ceiling prices for Brazil. Actual transaction prices may differ. Verify current CMED table at cmed.anvisa.gov.br before commercial use. Reference date not confirmed — treat as [INDICATIVE]."


def run(intake: dict) -> dict:
    molecule = intake.get("molecule")
    if not molecule:
        return {"found": False, "message": "No molecule identified for CMED lookup.", "evidence": "REQUIRES VALIDATION"}

    data = CMED_DATA.get(molecule)
    if data:
        return {
            "found":      True,
            "molecule":   molecule,
            "data":       {**data, "evidence": "INDICATIVE", "note": DISCLAIMER},
            "evidence":   "INDICATIVE",
            "disclaimer": DISCLAIMER,
        }

    return {
        "found":      False,
        "molecule":   molecule,
        "message":    f"No CMED reference data for '{molecule}'. Manual lookup required at cmed.anvisa.gov.br.",
        "evidence":   "REQUIRES VALIDATION",
        "disclaimer": DISCLAIMER,
    }
