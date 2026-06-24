"""Commercial Report Agent — assembles executive B2B report."""
from __future__ import annotations
from datetime import datetime, timezone


def run(intake: dict, regulatory: dict, cmed: dict, import_intel: dict,
        sourcing: dict, partner: dict, scoring: dict) -> dict:
    mol  = intake.get("molecule", "Not specified")
    area = intake.get("area", "Not specified")
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    L    = []

    def h(title: str) -> None:
        L.extend(["", f"{'─'*60}", title, f"{'─'*60}"])

    L.extend(["=" * 60, "PHARMAINTEL BR — MOLECULE OPPORTUNITY REPORT", f"Generated: {now}", "=" * 60])

    h("1. EXECUTIVE SUMMARY")
    L += [f"Molecule:          {mol.upper()}", f"Therapeutic Area:  {area}",
          f"Opportunity Level: {scoring.get('level', 'REQUIRES VALIDATION')}",
          f"Score:             {scoring.get('score', 0)}/100",
          f"Summary:           {scoring.get('summary', '')}"]

    h("2. REGULATORY SNAPSHOT [ANVISA]")
    if regulatory.get("found"):
        d = regulatory["data"]
        L += [f"Status:    {d.get('status', '')} [{d.get('evidence', 'INDICATIVE')}]",
              f"Category:  {d.get('category', '')}",
              f"Holders:   {', '.join(d.get('holders', []))}",
              f"Forms:     {', '.join(d.get('dosage_forms', []))}",
              f"Note:      {regulatory.get('note', '')}"]
    else:
        L += [f"Status:    {regulatory.get('message', 'No data')} [REQUIRES VALIDATION]"]

    h("3. CMED PRICING SNAPSHOT")
    if cmed.get("found"):
        d = cmed["data"]
        L += [f"Product:   {d.get('product', '')}",
              f"Company:   {d.get('company', '')}",
              f"PF Ref.:   {d.get('pf_sem_imp', '')} [INDICATIVE]",
              f"Note:      {d.get('note', '')}"]
    else:
        L += [f"Status:    {cmed.get('message', 'No data')} [REQUIRES VALIDATION]"]

    h("4. IMPORT INTELLIGENCE")
    if import_intel.get("found"):
        d = import_intel["data"]
        L += [f"NCM:         {d.get('ncm', '')}",
              f"Description: {d.get('description', '')}",
              f"FOB USD:     {d.get('fob_usd_2025', '')}",
              f"Origins:     {', '.join(d.get('top_origins', []))}",
              f"Trend:       {d.get('trend', '')}",
              f"Import Dep.: {d.get('import_dependence', '')} [ESTIMATED]",
              "", f"⚠  {import_intel.get('disclaimer', '')}"]
    else:
        L += [f"Status:    {import_intel.get('message', 'No data')}",
              f"⚠  {import_intel.get('disclaimer', '')}"]

    h("5. POTENTIAL BRAZILIAN PARTNER CATEGORIES")
    for b in partner.get("buyer_categories", []):
        L.append(f"  • {b}")
    if partner.get("known_reg_holders"):
        L += ["", "Known Registration Holders:"] + [f"  • {h_}" for h_ in partner["known_reg_holders"]]
    L += ["", f"Note: {partner.get('validation_note', '')} [INDICATIVE]"]

    h("6. RECOMMENDED SOURCING ROUTES")
    for r in sourcing.get("routes", []):
        L.append(f"  • {r}")
    L += ["", f"⚠  {sourcing.get('supplier_note', '')}"]

    h("7. MISSING INFORMATION & RISKS")
    for m in intake.get("missing", []):
        L.append(f"  • {m}")
    L += ["  • ANVISA data requires verification at consultas.anvisa.gov.br",
          "  • CMED prices require verification at cmed.anvisa.gov.br",
          "  • NCM data does not confirm molecule-specific revenue",
          "  • No verified international supplier database — active sourcing required"]

    h("8. OPPORTUNITY SCORE REASONING")
    for r in scoring.get("reasons", []):
        L.append(f"  • {r}")

    L.extend(["", "=" * 60,
               "PHARMAINTEL BR — CONFIDENTIAL COMMERCIAL INTELLIGENCE",
               "For B2B use only. All data requires validation before commercial use.",
               "Contact: business@globalhealthcareaccess.com",
               "Platform: https://pharmaintel-br.onrender.com/?page=partnership",
               "=" * 60])

    return {"report": "\n".join(L), "molecule": mol, "opportunity_level": scoring.get("level"), "score": scoring.get("score")}
