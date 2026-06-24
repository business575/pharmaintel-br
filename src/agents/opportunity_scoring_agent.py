"""Opportunity Scoring Agent — scores Brazil opportunity 0-100."""
from __future__ import annotations


def run(intake: dict, regulatory: dict, import_intel: dict, partner: dict) -> dict:
    score, reason = 0, []

    if regulatory.get("found"):
        holders = len((regulatory.get("data") or {}).get("holders", []))
        score += 30; reason.append(f"ANVISA registrations exist ({holders} known holders) [+30]")
    else:
        score += 5; reason.append("No confirmed ANVISA registrations — validation required [+5]")

    if import_intel.get("found"):
        dep = (import_intel.get("data") or {}).get("import_dependence", "")
        if "Very High" in dep:   score += 30; reason.append("Very high import dependence [+30]")
        elif "High" in dep:      score += 20; reason.append("High import dependence [+20]")
        elif "Medium" in dep:    score += 10; reason.append("Medium import dependence [+10]")
        else:                    score += 5;  reason.append("Low import dependence [+5]")
    else:
        reason.append("No import intelligence — NCM validation required [+0]")

    area = intake.get("area", "")
    if area in ("oncology", "plasma_derived", "rare_diseases", "glp1_metabolic"):
        score += 20; reason.append(f"High-value therapeutic area: {area} [+20]")
    elif area:
        score += 10; reason.append(f"Standard therapeutic area: {area} [+10]")

    if partner.get("known_reg_holders"):
        score += 10; reason.append("Known Brazilian registration holders identified [+10]")

    if intake.get("urgency") == "high":
        score += 10; reason.append("High urgency — immediate commercial window [+10]")

    if score >= 70:   level, summary = "HIGH OPPORTUNITY",       "Strong regulatory presence, significant import dependence and active buyer demand indicate a viable commercial opportunity."
    elif score >= 40: level, summary = "MEDIUM OPPORTUNITY",     "Moderate signals — opportunity exists but requires active sourcing and partner validation."
    elif score >= 20: level, summary = "LOW OPPORTUNITY",        "Limited signals — more research and validation required before commercial engagement."
    else:             level, summary = "REQUIRES VALIDATION",    "Insufficient data to score opportunity. Active validation required."

    return {
        "score":   score,
        "level":   level,
        "summary": summary,
        "reasons": reason,
        "note":    "Opportunity score is based on available curated data and does not constitute a commercial guarantee. Active validation required before investment.",
    }
