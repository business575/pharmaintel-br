"""
autonomous_sales_agent.py — Agente de vendas autônomo PharmaIntel BR

Fluxo:
1. Carrega leads do ANVISA (empresas com CNPJ ativo)
2. Busca contato via ReceitaWS API (grátis, sem auth)
3. Gera email personalizado com Groq/Llama
4. Envia via Resend
5. Faz follow-up automático após 3 dias
6. Detecta respostas de interesse e envia link de fechamento
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

ROOT         = Path(__file__).resolve().parents[2]
LEADS_FILE   = ROOT / "data" / "exports" / "auto_sales_leads.csv"
PROCESSED    = ROOT / "data" / "processed"

RESEND_KEY   = os.getenv("RESEND_API_KEY", "")
GROQ_KEY     = os.getenv("GROQ_API_KEY", "")
DEMO_URL     = "https://pharmaceuticaai.com"
STRIPE_STARTER  = "https://buy.stripe.com/starter"   # substituir pelo link real
STRIPE_PRO      = "https://buy.stripe.com/pro"
FROM_EMAIL   = "Vinicius Figueiredo <business@globalhealthcareaccess.com>"
DAILY_LIMIT  = 15


# ---------------------------------------------------------------------------
# Lead tracking
# ---------------------------------------------------------------------------

def _load_leads() -> list[dict]:
    if not LEADS_FILE.exists():
        return []
    with open(LEADS_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save_lead(lead: dict) -> None:
    LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    exists = LEADS_FILE.exists()
    with open(LEADS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "cnpj", "empresa", "email", "status", "data_envio",
            "followup_em", "resposta", "plano_recomendado", "notas"
        ])
        if not exists:
            writer.writeheader()
        writer.writerow(lead)


def _contacted_cnpjs() -> set:
    return {r["cnpj"] for r in _load_leads()}


# ---------------------------------------------------------------------------
# Lead sourcing — ANVISA empresas + dispositivos
# ---------------------------------------------------------------------------

def _get_prospects(limit: int = 50) -> list[dict]:
    """Carrega empresas do ANVISA com mais registros ativos."""
    prospects = []

    # Medicamentos
    emp_path = PROCESSED / "empresas_anvisa.parquet"
    if emp_path.exists():
        df = pd.read_parquet(emp_path)
        df = df[df["registros_ativos"] > 0].sort_values("registros_ativos", ascending=False)
        for _, row in df.head(limit).iterrows():
            prospects.append({
                "cnpj": str(row.get("cnpj", "")).strip(),
                "empresa": row.get("razao_social", ""),
                "segmento": "Medicamentos",
                "registros_ativos": int(row.get("registros_ativos", 0)),
                "pct_conformidade": float(row.get("pct_conformidade", 0)),
            })

    # Dispositivos médicos
    disp_path = PROCESSED / "anvisa_dispositivos.parquet"
    if disp_path.exists():
        import gc
        df2 = pd.read_parquet(disp_path, columns=["nu_cnpj_empresa", "no_razao_social_empresa",
                                                    "co_situacao_assunto_doc"])
        disp_summary = (
            df2.groupby("nu_cnpj_empresa")
            .agg(
                empresa=("no_razao_social_empresa", "first"),
                registros_ativos=("co_situacao_assunto_doc",
                                  lambda x: (x == "Publicado deferimento").sum()),
            )
            .reset_index()
            .rename(columns={"nu_cnpj_empresa": "cnpj"})
            .sort_values("registros_ativos", ascending=False)
        )
        del df2
        gc.collect()
        for _, row in disp_summary[disp_summary["registros_ativos"] > 5].head(30).iterrows():
            prospects.append({
                "cnpj": str(row.get("cnpj", "")).strip(),
                "empresa": row.get("empresa", ""),
                "segmento": "Dispositivos Médicos",
                "registros_ativos": int(row.get("registros_ativos", 0)),
                "pct_conformidade": 0.0,
            })

    return prospects


# ---------------------------------------------------------------------------
# Contact enrichment — ReceitaWS
# ---------------------------------------------------------------------------

def _get_contact_from_cnpj(cnpj: str) -> Optional[dict]:
    """Busca email e contato via ReceitaWS (API pública, sem auth)."""
    cnpj_clean = "".join(c for c in cnpj if c.isdigit())
    if len(cnpj_clean) != 14:
        return None
    try:
        r = httpx.get(f"https://receitaws.com.br/v1/cnpj/{cnpj_clean}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "ERROR":
                return None
            email = data.get("email", "").strip().lower()
            if not email or "@" not in email:
                return None
            return {
                "email": email,
                "nome_fantasia": data.get("fantasia", data.get("nome", "")),
                "municipio": data.get("municipio", ""),
                "uf": data.get("uf", ""),
                "telefone": data.get("telefone", ""),
                "porte": data.get("porte", ""),
                "situacao": data.get("situacao", ""),
            }
    except Exception as e:
        logger.warning(f"ReceitaWS error for {cnpj}: {e}")
    return None


# ---------------------------------------------------------------------------
# Email generation — Groq/Llama
# ---------------------------------------------------------------------------

def _generate_email_body(empresa: str, segmento: str, registros: int,
                          municipio: str, uf: str) -> str:
    """Gera corpo de email personalizado com Groq."""
    if not GROQ_KEY:
        return _fallback_email_body(empresa, segmento, registros)

    prompt = f"""Você é um especialista em vendas B2B de SaaS farmacêutico.
Escreva um email de prospecção frio em português brasileiro para a empresa:

- Nome: {empresa}
- Segmento: {segmento}
- Registros ANVISA ativos: {registros}
- Localização: {municipio}/{uf}

Regras:
- Máximo 4 parágrafos curtos
- Mencione dados REAIS: importações do Comex Stat, registros ANVISA, licitações ComprasNet
- Mostre que conhecemos o mercado DELES
- CTA claro: demo de 20 minutos ou link da plataforma
- Tom: direto, profissional, sem buzzwords
- NÃO use saudações genéricas
- Retorne APENAS o corpo do email em HTML simples (p, strong, ul, li)"""

    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-specdec",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.7,
            },
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Groq error: {e}")

    return _fallback_email_body(empresa, segmento, registros)


def _fallback_email_body(empresa: str, segmento: str, registros: int) -> str:
    return f"""<p>Olá equipe <strong>{empresa}</strong>,</p>
<p>Identificamos sua empresa no cadastro ANVISA com <strong>{registros} registros ativos</strong>
no segmento de <strong>{segmento}</strong>.</p>
<p>A <strong>PharmaIntel BR</strong> é a única plataforma que cruza dados do Comex Stat,
ANVISA e licitações públicas em tempo real — ajudando importadores como vocês a tomar
decisões mais rápidas e precisas.</p>
<p>Posso mostrar em <strong>20 minutos</strong> o que a plataforma entrega especificamente
para o perfil de vocês. Quando teria disponibilidade esta semana?</p>"""


# ---------------------------------------------------------------------------
# Email sending — Resend
# ---------------------------------------------------------------------------

def _send_email(to_email: str, empresa: str, body_html: str) -> bool:
    """Envia email via Brevo (primário) ou Resend (fallback)."""
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
  <div style="background:#0A1628;padding:20px;border-radius:8px 8px 0 0;">
    <h2 style="color:#4DB6AC;margin:0;">PharmaIntel BR</h2>
    <p style="color:#B0BEC5;margin:4px 0 0;font-size:13px;">Inteligência de Mercado Farmacêutico</p>
  </div>
  <div style="background:#ffffff;padding:28px;border:1px solid #e0e0e0;">
    {body_html}
    <div style="margin:24px 0;text-align:center;">
      <a href="https://calendly.com/vinicius-hospitalar/30min" style="background:#4DB6AC;color:#fff;padding:12px 28px;
         border-radius:6px;text-decoration:none;font-weight:700;">
        Agendar conversa de 30 min →
      </a>
    </div>
    <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
    <p style="color:#888;font-size:12px;margin:0;">
      <strong>Vinicius Figueiredo</strong> · CEO PharmaIntel BR<br>
      <a href="{DEMO_URL}" style="color:#4DB6AC;">{DEMO_URL}</a> ·
      business@globalhealthcareaccess.com · +55-21-97282-9820<br><br>
      Para cancelar o recebimento, responda com "cancelar".
    </p>
  </div>
</div>"""

    # ── Brevo (primário) ─────────────────────────────────────────────────────
    brevo_key = os.getenv("BREVO_API_KEY", "")
    if brevo_key:
        try:
            r = httpx.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": brevo_key, "Content-Type": "application/json"},
                json={
                    "sender":      {"name": "Vinicius Figueiredo", "email": "business@globalhealthcareaccess.com"},
                    "to":          [{"email": to_email}],
                    "replyTo":     {"email": "business@globalhealthcareaccess.com"},
                    "subject":     f"Inteligência de mercado para {empresa} — PharmaIntel BR",
                    "htmlContent": html,
                },
                timeout=15,
            )
            if r.status_code in (200, 201):
                return True
            logger.warning("Brevo error %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.warning(f"Brevo error: {e}")

    # ── Resend (fallback) ────────────────────────────────────────────────────
    if RESEND_KEY:
        try:
            r = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"},
                json={
                    "from":     FROM_EMAIL,
                    "reply_to": "business@globalhealthcareaccess.com",
                    "to":       [to_email],
                    "subject":  f"Inteligência de mercado para {empresa} — PharmaIntel BR",
                    "html":     html,
                },
                timeout=15,
            )
            return r.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Resend error: {e}")

    logger.error("Nenhum provedor configurado (BREVO_API_KEY ou RESEND_API_KEY)")
    return False


# ---------------------------------------------------------------------------
# Closing sequence — detecta interesse e envia Stripe
# ---------------------------------------------------------------------------

def _send_closing_email(to_email: str, empresa: str, plano: str = "pro") -> bool:
    """Envia email de fechamento com link Stripe."""
    stripe_url = STRIPE_PRO if plano == "pro" else STRIPE_STARTER
    plano_label = "Pro (R$ 697/mês)" if plano == "pro" else "Starter (R$ 297/mês)"

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
  <div style="background:#0A1628;padding:20px;border-radius:8px 8px 0 0;">
    <h2 style="color:#4DB6AC;margin:0;">PharmaIntel BR</h2>
  </div>
  <div style="background:#ffffff;padding:28px;border:1px solid #e0e0e0;">
    <p>Olá equipe <strong>{empresa}</strong>,</p>
    <p>Obrigado pelo interesse! Com base no perfil de vocês, recomendo o plano
    <strong>{plano_label}</strong>.</p>
    <p><strong>O que está incluso:</strong></p>
    <ul>
      <li>Dashboard completo Comex Stat + ANVISA + ComprasNet</li>
      <li>PHD Intel.AI — consultas ilimitadas</li>
      <li>Alertas de licitações por NCM</li>
      <li>Relatórios estratégicos em PDF</li>
    </ul>
    <div style="margin:24px 0;text-align:center;">
      <a href="{stripe_url}" style="background:#4DB6AC;color:#fff;padding:14px 32px;
         border-radius:6px;text-decoration:none;font-weight:700;font-size:16px;">
        Assinar Agora →
      </a>
    </div>
    <p style="color:#888;font-size:12px;">
      Cancele a qualquer momento. Acesso imediato após pagamento.<br>
      Dúvidas? Responda este email ou ligue: +55-21-97282-9820
    </p>
  </div>
</div>"""

    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"},
            json={
                "from": FROM_EMAIL,
                "reply_to": "business@globalhealthcareaccess.com",
                "to": [to_email],
                "subject": f"Seu acesso à PharmaIntel BR — {plano_label}",
                "html": html,
            },
            timeout=15,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        logger.error(f"Resend closing error: {e}")
        return False


# ---------------------------------------------------------------------------
# Follow-up — reengaja leads sem resposta após 3 dias
# ---------------------------------------------------------------------------

def _run_followups() -> int:
    """Envia follow-up para leads sem resposta após 3 dias."""
    leads = _load_leads()
    now = datetime.now(timezone.utc)
    sent = 0
    updated = []

    for lead in leads:
        if lead.get("status") != "enviado":
            updated.append(lead)
            continue
        followup_em = lead.get("followup_em", "")
        if not followup_em:
            updated.append(lead)
            continue
        try:
            dt = datetime.fromisoformat(followup_em)
            if dt > now:
                updated.append(lead)
                continue
        except Exception:
            updated.append(lead)
            continue

        # Envia follow-up
        body = f"""<p>Olá equipe <strong>{lead['empresa']}</strong>,</p>
<p>Enviei uma mensagem há alguns dias sobre a <strong>PharmaIntel BR</strong>.</p>
<p>Sei que a rotina é corrida. Deixo o link da plataforma para vocês explorarem
no tempo de vocês:</p>
<p><a href="{DEMO_URL}">{DEMO_URL}</a></p>
<p>Se preferirem, posso mostrar em <strong>15 minutos</strong> o que a plataforma
entrega especificamente para o perfil de vocês. Basta responder este email.</p>"""

        ok = _send_email(lead["email"], lead["empresa"], body)
        if ok:
            lead["status"] = "followup_enviado"
            lead["notas"] = (lead.get("notas", "") + " | followup enviado").strip(" | ")
            sent += 1
        updated.append(lead)

    # Reescreve o arquivo
    if updated:
        LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LEADS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=updated[0].keys())
            writer.writeheader()
            writer.writerows(updated)

    return sent


# ---------------------------------------------------------------------------
# Main — orquestra prospecção + fechamento
# ---------------------------------------------------------------------------

def run_daily_agent(dry_run: bool = False) -> dict:
    """
    Executa o ciclo diário do agente autônomo de vendas.
    dry_run=True: gera leads e emails mas não envia.
    """
    report = {
        "data": datetime.now(timezone.utc).isoformat(),
        "novos_enviados": 0,
        "followups_enviados": 0,
        "erros": 0,
        "leads_gerados": [],
    }

    already_contacted = _contacted_cnpjs()
    prospects = _get_prospects(limit=100)

    # Filtra já contactados
    new_prospects = [p for p in prospects if p["cnpj"] not in already_contacted]
    logger.info(f"Prospects disponíveis: {len(new_prospects)}")

    sent_today = 0
    for prospect in new_prospects:
        if sent_today >= DAILY_LIMIT:
            break

        cnpj = prospect["cnpj"]
        empresa = prospect["empresa"]
        segmento = prospect["segmento"]
        registros = prospect["registros_ativos"]

        # Busca contato
        contact = _get_contact_from_cnpj(cnpj)
        if not contact or not contact.get("email"):
            logger.info(f"Sem email para {empresa} ({cnpj})")
            continue

        if contact.get("situacao", "").upper() != "ATIVA":
            continue

        email = contact["email"]
        municipio = contact.get("municipio", "")
        uf = contact.get("uf", "")

        # Gera email personalizado
        body = _generate_email_body(empresa, segmento, registros, municipio, uf)

        # Envia
        if not dry_run:
            ok = _send_email(email, empresa, body)
            time.sleep(1)  # rate limit
        else:
            ok = True
            logger.info(f"[DRY RUN] Enviaria para {email} ({empresa})")

        followup_em = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        plano = "pro" if registros > 20 else "starter"

        lead_record = {
            "cnpj": cnpj,
            "empresa": empresa,
            "email": email,
            "status": "enviado" if ok else "erro",
            "data_envio": datetime.now(timezone.utc).isoformat(),
            "followup_em": followup_em,
            "resposta": "",
            "plano_recomendado": plano,
            "notas": f"{segmento} | {registros} registros | {municipio}/{uf}",
        }

        if not dry_run:
            _save_lead(lead_record)

        report["leads_gerados"].append({
            "empresa": empresa,
            "email": email,
            "status": "enviado" if ok else "erro",
        })

        if ok:
            report["novos_enviados"] += 1
            sent_today += 1
        else:
            report["erros"] += 1

    # Follow-ups
    if not dry_run:
        report["followups_enviados"] = _run_followups()

    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    dry = "--dry-run" in sys.argv
    result = run_daily_agent(dry_run=dry)
    print(json.dumps(result, indent=2, ensure_ascii=False))
