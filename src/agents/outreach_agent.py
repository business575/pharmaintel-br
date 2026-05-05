"""
outreach_agent.py — PharmaIntel BR Sales Outreach Agent

Contacts 10-20 prospects per day with personalized emails presenting
the platform. Tracks all contacts in the prospects table.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

RESEND_FROM  = "PharmaIntel BR <business@globalhealthcareaccess.com>"
DEMO_URL     = "https://pharmaintel-br.onrender.com"
CALENDLY_URL = "https://calendly.com/vinicius-hospitalar/30min"
DAILY_LIMIT  = 20


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

def _is_international(company: dict) -> bool:
    """Detect international prospects by email domain, description or segment."""
    email = company.get("email", "")
    desc  = (company.get("description", "") + " " + company.get("segment", "")).lower()
    intl_tlds = (".ch", ".us", ".uk", ".de", ".fr", ".cn", ".in", ".jp", ".ca", ".au")
    if any(email.endswith(t) for t in intl_tlds):
        return True
    intl_keywords = (
        "switzerland", "suíça", "uk ", "german", "french", "china", "chinese",
        "us biotech", "uk biotech", "spanish", "swedish", "irish", "italian",
        "latam", "latin america", "international", "global", "europe",
    )
    return any(kw in desc for kw in intl_keywords)


def _build_email_en(company: dict, ai_body: str) -> tuple[str, str]:
    """Return (subject, html_body) in EN with USD pricing."""
    role = company.get("contact_role", "Team")
    name = company.get("company_name", "")
    subject = f"Brazilian Pharma Market Intelligence for {name}"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1a1a2e;">
  <div style="background:#0A1628;padding:24px;border-radius:8px 8px 0 0;text-align:center;">
    <h2 style="color:#4DB6AC;margin:0;">PharmaIntel BR</h2>
    <p style="color:#B0BEC5;margin:4px 0 0;font-size:13px;">Brazilian Pharmaceutical Market Intelligence</p>
  </div>
  <div style="background:#ffffff;padding:28px;border:1px solid #e0e0e0;border-top:none;">
    <p>Hello <strong>{role}</strong> at <strong>{name}</strong>,</p>
    {ai_body}
    <div style="background:#f5f9ff;border-left:4px solid #4DB6AC;padding:16px;margin:20px 0;border-radius:4px;">
      <p style="margin:0 0 8px;font-weight:600;color:#0A1628;">Plans starting at <strong>US$ 299/month</strong>:</p>
      <p style="margin:0;font-size:13px;color:#333;">
        Starter: US$ 299/mo · Pro: US$ 499/mo · Enterprise: US$ 1,499/mo
      </p>
    </div>
    <div style="background:#f5f9ff;border-left:4px solid #00897B;padding:16px;margin:20px 0;border-radius:4px;">
      <p style="margin:0;font-weight:600;color:#0A1628;">Try the free AI demo:</p>
      <a href="{DEMO_URL}" style="color:#00897B;font-size:15px;">{DEMO_URL}</a>
    </div>
    <div style="text-align:center;margin:24px 0;">
      <a href="{CALENDLY_URL}" style="background:#4DB6AC;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;font-size:15px;">
        Book a 30-min call →
      </a>
    </div>
    <p>Happy to show you exactly what we track for your market.</p>
    <p>Best regards,<br>
    <strong>Vinicius</strong><br>
    PharmaIntel BR<br>
    <span style="color:#888;font-size:12px;">Strategic intelligence for pharma importers in Brazil</span>
    </p>
  </div>
  <div style="background:#f5f5f5;padding:12px;text-align:center;font-size:11px;color:#999;border-radius:0 0 8px 8px;">
    To unsubscribe, reply with "Remove".
  </div>
</div>"""
    return subject, html


def _build_email_pt(company: dict, ai_body: str) -> tuple[str, str]:
    """Return (subject, html_body) in PT."""
    role   = company.get("contact_role", "Equipe")
    name   = company.get("company_name", "")
    subject = f"Inteligência de mercado farmacêutico para {name}"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1a1a2e;">
  <div style="background:#0A1628;padding:24px;border-radius:8px 8px 0 0;text-align:center;">
    <h2 style="color:#4DB6AC;margin:0;">PharmaIntel BR</h2>
    <p style="color:#B0BEC5;margin:4px 0 0;font-size:13px;">Inteligência de Mercado Farmacêutico</p>
  </div>
  <div style="background:#ffffff;padding:28px;border:1px solid #e0e0e0;border-top:none;">
    <p>Olá, equipe {role} da <strong>{name}</strong>,</p>
    {ai_body}
    <div style="background:#f5f9ff;border-left:4px solid #4DB6AC;padding:16px;margin:20px 0;border-radius:4px;">
      <p style="margin:0;font-weight:600;color:#0A1628;">Acesse a demonstração gratuita:</p>
      <a href="{DEMO_URL}" style="color:#00897B;font-size:15px;">{DEMO_URL}</a>
    </div>
    <div style="text-align:center;margin:24px 0;">
      <a href="{CALENDLY_URL}" style="background:#4DB6AC;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;font-size:15px;">
        Agendar conversa de 30 min →
      </a>
    </div>
    <p>Posso mostrar em 30 minutos o que a plataforma entrega para o perfil de vocês.</p>
    <p>Atenciosamente,<br>
    <strong>Vinicius</strong><br>
    PharmaIntel BR<br>
    <span style="color:#888;font-size:12px;">Inteligência estratégica para importadores farmacêuticos</span>
    </p>
  </div>
  <div style="background:#f5f5f5;padding:12px;text-align:center;font-size:11px;color:#999;border-radius:0 0 8px 8px;">
    Para remover seu email desta lista, responda com "Remover".
  </div>
</div>"""
    return subject, html


def _build_partner_email_pt(company: dict, ai_body: str) -> tuple[str, str]:
    """Return (subject, html) for strategic partner outreach."""
    name    = company.get("company_name", "")
    subject = f"Parceria estratégica — PharmaIntel BR × {name}"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1a1a2e;">
  <div style="background:#0A1628;padding:24px;border-radius:8px 8px 0 0;text-align:center;">
    <h2 style="color:#26C6DA;margin:0;">PharmaIntel BR</h2>
    <p style="color:#B0BEC5;margin:4px 0 0;font-size:13px;">Proposta de Parceria Estratégica</p>
  </div>
  <div style="background:#ffffff;padding:28px;border:1px solid #e0e0e0;border-top:none;">
    <p>Olá, equipe <strong>{name}</strong>,</p>
    {ai_body}
    <div style="background:#f5f9ff;border-left:4px solid #26C6DA;padding:16px;margin:20px 0;border-radius:4px;">
      <p style="margin:0;font-weight:600;color:#0A1628;">Conheça a plataforma:</p>
      <a href="{DEMO_URL}" style="color:#00897B;">{DEMO_URL}</a>
    </div>
    <div style="text-align:center;margin:24px 0;">
      <a href="{CALENDLY_URL}" style="background:#26C6DA;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;font-size:15px;">
        Agendar call de 30 min →
      </a>
    </div>
    <p>Podemos explorar as oportunidades em 30 minutos — quando tiver disponibilidade?</p>
    <p>Atenciosamente,<br><strong>Vinicius</strong><br>PharmaIntel BR</p>
  </div>
</div>"""
    return subject, html


# ---------------------------------------------------------------------------
# AI body generation
# ---------------------------------------------------------------------------

def _generate_email_body(company: dict, lang: str = "PT") -> str:
    """Use Groq/Anthropic to generate personalized email body paragraphs."""
    name        = company.get("company_name", "a empresa")
    description = company.get("description", "")
    segment     = company.get("segment", "")
    role        = company.get("contact_role", "")
    is_partner  = company.get("is_partner", False)

    if is_partner:
        prompt = f"""Escreva 2 parágrafos curtos (máx 80 palavras cada) de um email de proposta de parceria estratégica.
Empresa: {name}
Descrição: {description}
Contexto: PharmaIntel BR é uma plataforma SaaS de inteligência de mercado farmacêutico brasileiro (Comex Stat, ANVISA, ComprasNet).
A parceria seria para co-venda ou referência de clientes importadores.
Tom: profissional, direto, proposta de valor clara. Sem exageros. Apenas os parágrafos em HTML (<p> tags)."""
    elif lang == "EN":
        prompt = f"""Write 2 short paragraphs (max 80 words each) for a cold sales email to:
Company: {name}
Segment: {segment}
Description: {description}
Target contact: {role}

Product: PharmaIntel BR — SaaS platform with real-time Brazilian pharma import data (Comex Stat),
ANVISA monitoring (17,247 registrations), expiry alerts, competitor analysis and strategic AI.
Plans: Starter US$299/mo · Pro US$499/mo · Enterprise US$1,499/mo.

Mention 1-2 specific benefits for this company's profile.
Tone: executive, direct, no fluff. Output only the paragraphs in HTML (<p> tags)."""
    else:
        prompt = f"""Escreva 2 parágrafos curtos (máx 80 palavras cada) de prospecção de vendas para:
Empresa: {name}
Segmento: {segment}
Descrição: {description}
Contato alvo: {role}

Produto: PharmaIntel BR — plataforma SaaS com dados de importação farmacêutica em tempo real (Comex Stat),
monitoramento ANVISA (17.247 registros), alertas de vencimento, análise de concorrentes e IA estratégica.

Mencione 1-2 benefícios específicos para o perfil desta empresa.
Tom: executivo, direto, sem enrolar. Apenas os parágrafos em HTML (<p> tags)."""

    # Try Anthropic first
    try:
        import anthropic as _ant
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if key:
            client = _ant.Anthropic(api_key=key)
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
    except Exception as exc:
        logger.warning("Anthropic body gen failed: %s", exc)

    # Groq fallback
    try:
        from groq import Groq
        key = os.getenv("GROQ_API_KEY", "")
        if key:
            client = Groq(api_key=key)
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            )
            return resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Groq body gen failed: %s", exc)

    # Static fallback
    if is_partner:
        return (
            f"<p>Gostaríamos de explorar uma parceria estratégica entre {name} e PharmaIntel BR, "
            f"plataforma de inteligência de mercado farmacêutico com dados de importação em tempo real.</p>"
            f"<p>Acreditamos que podemos criar valor mútuo para nossos clientes no mercado farmacêutico brasileiro.</p>"
        )
    return (
        f"<p>A PharmaIntel BR oferece inteligência de mercado farmacêutico com dados reais do Comex Stat, "
        f"monitoramento ANVISA e análise competitiva — tudo numa única plataforma.</p>"
        f"<p>Para empresas como {name}, isso significa visibilidade completa sobre importações, "
        f"concorrentes e oportunidades de mercado em tempo real.</p>"
    )


# ---------------------------------------------------------------------------
# Send email
# ---------------------------------------------------------------------------

def _send_outreach_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send via Gmail SMTP (primary), Brevo or Resend (fallback)."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    # ── Gmail SMTP (primary) ─────────────────────────────────────────────────
    gmail_user = os.getenv("GMAIL_USER", "")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")
    if gmail_user and gmail_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"]    = f"Vinicius Figueiredo | PharmaIntel BR <{gmail_user}>"
            msg["To"]      = to_email
            msg["Subject"] = subject
            msg["Reply-To"] = gmail_user
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(gmail_user, gmail_pass)
                server.sendmail(gmail_user, to_email, msg.as_string())
            return True
        except Exception as exc:
            logger.warning("Gmail SMTP failed: %s", exc)

    # ── Brevo (fallback) ─────────────────────────────────────────────────────
    brevo_key = os.getenv("BREVO_API_KEY", "")
    if brevo_key:
        try:
            import httpx as _httpx
            r = _httpx.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": brevo_key, "Content-Type": "application/json"},
                json={"sender": {"name": "Vinicius Figueiredo", "email": gmail_user or "business@globalhealthcareaccess.com"},
                      "to": [{"email": to_email}], "subject": subject, "htmlContent": html_body},
                timeout=15,
            )
            if r.status_code in (200, 201):
                return True
        except Exception as exc:
            logger.warning("Brevo failed: %s", exc)

    logger.error("Nenhum provedor de email configurado")
    return False


# ---------------------------------------------------------------------------
# Main outreach runner
# ---------------------------------------------------------------------------

def run_daily_outreach(daily_limit: int = DAILY_LIMIT, dry_run: bool = False) -> dict:
    """
    Run the daily outreach campaign.
    Returns summary dict with sent/failed counts and list of contacts made.
    """
    from src.db.database import init_db, get_prospects_due_today, update_prospect
    init_db()

    prospects = get_prospects_due_today(daily_limit=daily_limit)
    sent = []
    failed = []
    now = datetime.now(timezone.utc)

    for company in prospects:
        pid        = company["id"]
        email      = company["email"]
        is_partner = company.get("is_partner", False)

        # Detect language
        intl = _is_international(company)
        lang = "EN" if intl else "PT"

        # Generate personalized body
        body = _generate_email_body(company, lang=lang)

        # Build email
        if is_partner:
            subject, html = _build_partner_email_pt(company, body)
        elif intl:
            subject, html = _build_email_en(company, body)
        else:
            subject, html = _build_email_pt(company, body)

        if dry_run:
            sent.append({"company": company["company_name"], "email": email, "subject": subject, "dry_run": True})
            continue

        success = _send_outreach_email(email, subject, html)
        if success:
            update_prospect(pid,
                status="contacted",
                last_contact=now,
                emails_sent=company.get("emails_sent", 0) + 1,
                last_email_body=html[:2000],
            )
            sent.append({"company": company["company_name"], "email": email})
            logger.info("Outreach sent → %s <%s>", company["company_name"], email)
        else:
            failed.append({"company": company["company_name"], "email": email})

    return {
        "sent": len(sent),
        "failed": len(failed),
        "contacts": sent,
        "errors": failed,
        "timestamp": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Seed initial prospects
# ---------------------------------------------------------------------------

def seed_prospects() -> None:
    """Load the initial prospect list into DB."""
    from src.db.database import init_db, add_prospect
    init_db()

    prospects = [
        {
            "company_name": "Pharmedic Pharmaceuticals",
            "email": "pharmedic@pharmedic.com.br",
            "phone": "+55 (11) 5581-6476",
            "contact_role": "Diretor",
            "segment": "Medicamentos importados, doenças raras",
            "description": "Foco em medicamentos importados e doenças raras.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "SPH Medical",
            "email": "",  # no email yet — will be filled when found
            "phone": "",
            "contact_role": "Diretor de Importação",
            "segment": "Medicamentos internacionais",
            "description": "Importação e distribuição de medicamentos internacionais.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "Pharmove",
            "email": "",
            "phone": "",
            "contact_role": "Regulatory + Business Development",
            "segment": "Importação, registro, nacionalização",
            "description": "Especialista em importação, registro e nacionalização de medicamentos.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "Belpharma",
            "email": "",
            "phone": "",
            "contact_role": "Supply / Sourcing",
            "segment": "APIs, insumos farmacêuticos",
            "description": "Forte em APIs e importação de insumos farmacêuticos.",
            "is_partner": False,
            "priority": "medium",
        },
        {
            "company_name": "Brisa Advisors",
            "email": "contactBR@brisa.com.br",
            "phone": "+55 (21) 98823-0888",
            "contact_role": "Parceiro Estratégico",
            "segment": "Consultoria, entrada de empresas internacionais no Brasil",
            "description": "Atua trazendo empresas internacionais para o mercado farmacêutico brasileiro.",
            "is_partner": True,
            "priority": "high",
        },
        {
            "company_name": "Grupo Cimed",
            "email": "joao@grupocimed.com.br",
            "phone": "",
            "contact_role": "Diretor",
            "segment": "Medicamentos genéricos e branded",
            "description": "Um dos maiores grupos farmacêuticos do Brasil, forte atuação em medicamentos genéricos, branded e OTC.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "Global Swiss Group",
            "email": "charyyeva.t@global-swiss.ch",
            "phone": "+41 79 2933822",
            "contact_role": "General Manager of Sales — USA / Canada / LATAM",
            "segment": "Distribuição farmacêutica internacional, LATAM",
            "description": "Global Swiss Group — Suíça. Tatyana Charyyeva gerencia vendas para USA, Canada e LATAM. Contactada via LinkedIn. Potencial cliente Enterprise para inteligência do mercado farmacêutico brasileiro.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "Grupo Cimed",
            "email": "marisa.tomazela@grupocimed.com.br",
            "phone": "",
            "contact_role": "Gerente / Diretora",
            "segment": "Medicamentos genéricos e branded",
            "description": "Um dos maiores grupos farmacêuticos do Brasil, forte atuação em medicamentos genéricos, branded e OTC.",
            "is_partner": False,
            "priority": "high",
        },
        # ── Global Pipeline — International Biotech/Pharma ──────────────────
        {
            "company_name": "Athernal Bio",
            "email": "info@athernalbio.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Immunotherapies, rare blood disorders",
            "description": "UK biotech developing immunotherapies for rare blood disorders and clonal hematopoiesis. Clinical stage.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "Athos Therapeutics",
            "email": "info@athostx.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "AI-based precision therapeutics, IBD, oncology",
            "description": "US biotech using AI for precision therapeutics — IBD, lupus, oncology. Clinical stage.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "Atlanthera",
            "email": "contact@atlanthera.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Bone disease treatments, oncology",
            "description": "French biotech focused on bone cancer and osteoarthritis treatments.",
            "is_partner": False,
            "priority": "medium",
        },
        {
            "company_name": "Atlas Molecular Pharma",
            "email": "info@atlasmolecularpharma.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Rare diseases, pharmacological chaperones",
            "description": "Spanish biotech — drug discovery for rare diseases including porphyria and prion disease.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "Atom Therapeutics",
            "email": "info@atombp.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Small molecules, metabolic diseases, gout",
            "description": "China-based biotech with small molecules for metabolic diseases — gout, CKD, cardiovascular.",
            "is_partner": False,
            "priority": "medium",
        },
        {
            "company_name": "Atriva Therapeutics",
            "email": "info@atriva-therapeutics.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Antiviral, respiratory infections",
            "description": "German biotech — inhibitors against respiratory viral infections including COVID-19, influenza, RSV.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "Atropos Therapeutics",
            "email": "info@atroposthera.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Small molecules, senescence, aging, oncology",
            "description": "US biotech targeting senescence with small molecules for aging-related diseases and oncology.",
            "is_partner": False,
            "priority": "medium",
        },
        {
            "company_name": "Atsena Therapeutics",
            "email": "info@atsenatx.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Gene therapy, ophthalmology, rare diseases",
            "description": "US gene therapy company targeting rare eye diseases — Leber congenital amaurosis, X-linked retinoschisis.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "Atterx BioTherapeutics",
            "email": "info@conjugon.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Biologics, infectious disease",
            "description": "US biotech developing biologics for catheter-associated UTI and bacterial infections.",
            "is_partner": False,
            "priority": "medium",
        },
        {
            "company_name": "AttgeNO",
            "email": "info@attgeno.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Cardiovascular, pulmonary hypertension",
            "description": "Swedish biotech — nitric-oxide donating drugs for pulmonary hypertension, embolism and cardiovascular.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "ATXA Therapeutics",
            "email": "info@atxatherapeutics.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Cardiopulmonary, PAH",
            "description": "Irish biotech treating pulmonary arterial hypertension with small molecules.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "aTyr Pharma",
            "email": "info@atyrpharma.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Therapeutic proteins, pulmonary, immunology",
            "description": "US biotech with therapeutic proteins for pulmonary sarcoidosis, ILD and fibrosis.",
            "is_partner": False,
            "priority": "high",
        },
        {
            "company_name": "AudioCure Pharma",
            "email": "info@audiocure.com",
            "phone": "",
            "contact_role": "Business Development",
            "segment": "Otology, inner ear treatments",
            "description": "German biotech treating sudden sensorineural hearing loss — Phase 2 clinical.",
            "is_partner": False,
            "priority": "medium",
        },
    ]

    added = 0
    for p in prospects:
        if p["email"]:  # only add if we have an email
            add_prospect(**p)
            added += 1

    logger.info("Seeded %d prospects", added)
    return added
