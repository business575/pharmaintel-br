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

RESEND_FROM = "PharmaIntel BR <onboarding@resend.dev>"
DEMO_URL    = "https://pharmaintel-br.onrender.com"
DAILY_LIMIT = 20


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

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
    <p>Disponível para uma conversa de 15 minutos esta semana.</p>
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
    <p>Podemos agendar uma call esta semana para explorar as oportunidades?</p>
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
    """Send via Resend. Returns True on success."""
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY", "")
        if not resend.api_key:
            logger.error("RESEND_API_KEY not set")
            return False
        resend.Emails.send({
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })
        return True
    except Exception as exc:
        logger.error("Send outreach email failed: %s", exc)
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

        # Generate personalized body
        body = _generate_email_body(company)

        # Build email
        if is_partner:
            subject, html = _build_partner_email_pt(company, body)
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
    ]

    added = 0
    for p in prospects:
        if p["email"]:  # only add if we have an email
            add_prospect(**p)
            added += 1

    logger.info("Seeded %d prospects", added)
    return added
