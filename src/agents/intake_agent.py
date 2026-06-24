"""Intake Agent — classifies request and extracts entities."""
from __future__ import annotations

MOLECULE_KEYWORDS: dict[str, list[str]] = {
    "trastuzumab":   ["trastuzumab", "trastuzumabe", "herceptin"],
    "semaglutide":   ["semaglutide", "semaglutida", "ozempic", "wegovy"],
    "pembrolizumab": ["pembrolizumab", "pembrolizumabe", "keytruda"],
    "bevacizumab":   ["bevacizumab", "bevacizumabe", "avastin"],
    "rituximab":     ["rituximab", "rituximabe", "mabthera"],
    "nivolumab":     ["nivolumab", "nivolumabe", "opdivo"],
    "imatinib":      ["imatinib", "imatinibe", "gleevec"],
    "paclitaxel":    ["paclitaxel"],
    "docetaxel":     ["docetaxel"],
    "capecitabine":  ["capecitabine", "capecitabina", "xeloda"],
    "albumin":       ["albumin", "albumina", "hsa", "human serum albumin"],
    "immunoglobulin":["immunoglobulin", "imunoglobulina", "ivig", "igiv"],
    "adalimumab":    ["adalimumab", "adalimumabe", "humira"],
    "infliximab":    ["infliximab", "infliximabe", "remicade"],
    "filgrastim":    ["filgrastim", "neupogen"],
    "levetiracetam": ["levetiracetam", "keppra"],
    "tacrolimus":    ["tacrolimus", "prograf"],
    "mycophenolate": ["mycophenolate", "micofenolato"],
    "omeprazole":    ["omeprazole", "omeprazol"],
    "methotrexate":  ["methotrexate", "metotrexato"],
}

AREA_KEYWORDS: dict[str, list[str]] = {
    "oncology":      ["oncolog", "cancer", "tumor", "antineoplastic", "trastuzumab", "trastuzumabe", "herceptin", "bevacizumab", "bevacizumabe", "avastin", "rituximab", "rituximabe", "mabthera", "pembrolizumab", "pembrolizumabe", "keytruda", "nivolumab", "nivolumabe", "opdivo", "paclitaxel", "docetaxel", "imatinib", "capecitabine"],
    "immunology":    ["immunol", "imunol", "autoimmune", "autoimune", "transplant", "tacrolimus", "mycophenolate"],
    "rare_diseases": ["rare disease", "doença rara", "orphan", "órfão"],
    "cns":           ["cns", "snc", "neurol", "epileps", "psychiatric", "psiquiatr", "levetiracetam"],
    "plasma_derived":["albumin", "albumina", "immunoglobulin", "imunoglobulina", "plasma", "ivig"],
    "glp1_metabolic":["glp-1", "glp1", "semaglutide", "liraglutide", "obesity", "diabetes"],
    "cardiology":    ["cardio", "cardiac", "heart", "cardiovasc"],
    "infectology":   ["antibiotic", "antibiótico", "infectol", "antimicrob"],
}

TYPE_KEYWORDS: dict[str, list[str]] = {
    "api_ifa_sourcing":            ["api", "ifa", "active ingredient", "ingrediente ativo", "bulk"],
    "fdf_opportunity":             ["fdf", "finished dosage", "forma farmacêutica", "tablet", "capsule", "injectable", "sachet", "softgel"],
    "cdmo_opportunity":            ["cdmo", "contract manufactur", "fill-finish", "toll manufactur"],
    "brazil_market_entry":         ["market entry", "enter brazil", "entrada no brasil", "enter the brazilian"],
    "molecule_opportunity_report": ["opportunity report", "evaluate", "avali", "opportunity for", "oportunidade"],
    "anvisa_cmed_lookup":          ["anvisa", "cmed", "registration", "registro"],
    "import_intelligence":         ["import", "importa", "ncm", "comex", "mdic"],
    "partner_mapping":             ["partner", "parceiro", "buyer", "comprador", "distributor"],
    "commercial_proposal":         ["proposal", "proposta", "service", "serviço", "contrato"],
}

URGENCY_KEYWORDS: dict[str, list[str]] = {
    "high":   ["urgent", "urgente", "asap", "immediately", "imediato", "now", "agora", "this week"],
    "medium": ["soon", "em breve", "next month", "próximo mês", "within 30"],
    "low":    ["exploratory", "exploratório", "long term", "longo prazo", "future"],
}


def run(request: str) -> dict:
    text = request.lower()

    request_type = "molecule_opportunity_report"
    best_score = 0
    for rtype, kws in TYPE_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text)
        if score > best_score:
            best_score = score
            request_type = rtype

    molecule = next((mol for mol, aliases in MOLECULE_KEYWORDS.items() if any(a in text for a in aliases)), None)
    area     = next((a for a, kws in AREA_KEYWORDS.items() if any(kw in text for kw in kws)), None)

    dosage_form = next((f for f in ["tablet", "capsule", "injectable", "sachet", "vial", "softgel"] if f in text), None)
    company_type = next((ct for ct in ["api manufacturer", "cdmo", "fdf manufacturer", "distributor", "importer"] if ct in text), None)
    country = next((c for c in ["india", "china", "germany", "france", "italy", "korea", "brazil", "brasil"] if c in text), None)
    urgency = next((u for u, kws in URGENCY_KEYWORDS.items() if any(kw in text for kw in kws)), "medium")

    missing = []
    if not molecule:
        missing.append("molecule/active ingredient not specified")
    if not area:
        missing.append("therapeutic area not specified")
    if request_type in ("brazil_market_entry", "api_ifa_sourcing") and not country:
        missing.append("supplier country not specified")

    return {
        "request_type": request_type,
        "molecule":     molecule,
        "area":         area,
        "dosage_form":  dosage_form,
        "company_type": company_type,
        "country":      country,
        "urgency":      urgency,
        "missing":      missing,
        "raw_request":  request,
    }
