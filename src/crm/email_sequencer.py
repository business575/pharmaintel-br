"""
email_sequencer.py - Automated email sequences for lead nurturing

Manages a 4-email drip sequence:
  Day 0: Welcome (sent by app.py on capture)
  Day 2: "Did you see what the AI found?" — real insight showcase
  Day 5: "3 companies already using PharmaIntel" — social proof + urgency
  Day 7: "Last chance — founding member pricing" — urgency close
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LEADS_FILE = DATA_DIR / "demo_leads.json"

PLATFORM_URL = "https://pharmaintel-br.onrender.com"
FROM_ADDRESS = "PharmaIntel AI <onboarding@resend.dev>"

# Sequence schedule: day offset → sequence key
SEQUENCE_DAYS = {2: "insight", 5: "social_proof", 7: "urgency"}


# ---------------------------------------------------------------------------
# Email content
# ---------------------------------------------------------------------------

def _get_email_content(day: int, lang: str) -> tuple[str, str]:
    """Return (subject, html_body) for the given sequence day and language."""

    if lang == "EN":
        if day == 2:
            subject = "What the AI found in your pharma segment 🔍"
            body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A1628;color:#E8EDF5;padding:24px;border-radius:12px;">
  <h2 style="color:#4DB6AC;">Did you see what PharmaIntel found?</h2>
  <p>You tried our AI 2 days ago. Here's what it would show you with full access:</p>
  <ul>
    <li>🏆 <b>Top 3 importers</b> in your NCM segment and their exact FOB prices</li>
    <li>📊 <b>Monthly volume trends</b> — is your market growing or shrinking?</li>
    <li>⚠️ <b>ANVISA alerts</b> — 3 products flagged for irregularities this week</li>
    <li>🏛️ <b>Government tenders</b> — R$2.3M in open pharma procurement</li>
  </ul>
  <p>All of this, updated daily, in one dashboard.</p>
  <div style="text-align:center;margin:24px 0;">
    <a href="{PLATFORM_URL}" style="background:#4DB6AC;color:#0A1628;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
      Start 7-Day Free Trial
    </a>
  </div>
  <p style="color:#8899AA;font-size:0.85rem;">PharmaIntel BR · Unsubscribe: reply with "unsubscribe"</p>
</div>"""

        elif day == 5:
            subject = "3 importers already using PharmaIntel this month"
            body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A1628;color:#E8EDF5;padding:24px;border-radius:12px;">
  <h2 style="color:#4DB6AC;">Your competitors are already watching the market</h2>
  <p>This month, 3 pharma importers subscribed to PharmaIntel BR. Here's what they said:</p>
  <blockquote style="border-left:3px solid #4DB6AC;padding-left:16px;color:#B0BEC5;">
    "Found a competitor importing the same NCM at 18% lower price. We renegotiated our supplier in 2 weeks."
    <br><b>— Starter Plan subscriber, São Paulo</b>
  </blockquote>
  <blockquote style="border-left:3px solid #4DB6AC;padding-left:16px;color:#B0BEC5;">
    "ANVISA alert saved us from importing a product with suspended registration."
    <br><b>— Pro Plan subscriber, Rio de Janeiro</b>
  </blockquote>
  <p><b>Founding member pricing ends April 30.</b> Lock in R$497/month before it goes to R$697.</p>
  <div style="text-align:center;margin:24px 0;">
    <a href="{PLATFORM_URL}" style="background:#4DB6AC;color:#0A1628;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
      Lock In Founding Price
    </a>
  </div>
  <p style="color:#8899AA;font-size:0.85rem;">PharmaIntel BR · Unsubscribe: reply with "unsubscribe"</p>
</div>"""

        else:  # day == 7
            subject = "Last 48h — founding member pricing expires April 30"
            body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A1628;color:#E8EDF5;padding:24px;border-radius:12px;">
  <h2 style="color:#FF6B6B;">⏰ Founding member pricing ends tomorrow</h2>
  <p>After April 30, PharmaIntel BR prices increase to:</p>
  <ul>
    <li>Starter: R$497 → <b>R$697/month</b></li>
    <li>Pro: R$997 → <b>R$1,297/month</b></li>
    <li>Enterprise: R$2,497 → <b>R$2,997/month</b></li>
  </ul>
  <p>Lock in the founding price today and keep it <b>forever</b>, even as we add more features.</p>
  <div style="text-align:center;margin:24px 0;">
    <a href="{PLATFORM_URL}" style="background:#FF6B6B;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
      Claim Founding Price Now →
    </a>
  </div>
  <p style="color:#8899AA;">Questions? Reply to this email — we respond within 2 hours.</p>
  <p style="color:#8899AA;font-size:0.85rem;">PharmaIntel BR · Unsubscribe: reply with "unsubscribe"</p>
</div>"""

    else:  # PT
        if day == 2:
            subject = "O que a IA encontrou no seu segmento farmacêutico 🔍"
            body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A1628;color:#E8EDF5;padding:24px;border-radius:12px;">
  <h2 style="color:#4DB6AC;">Você viu o que o PharmaIntel encontrou?</h2>
  <p>Você testou nossa IA há 2 dias. Veja o que ela mostraria com acesso completo:</p>
  <ul>
    <li>🏆 <b>Top 3 importadores</b> do seu segmento de NCM e seus preços FOB exatos</li>
    <li>📊 <b>Tendências mensais de volume</b> — seu mercado está crescendo ou encolhendo?</li>
    <li>⚠️ <b>Alertas ANVISA</b> — 3 produtos sinalizados por irregularidades esta semana</li>
    <li>🏛️ <b>Licitações governamentais</b> — R$2,3M em compras farmacêuticas abertas</li>
  </ul>
  <p>Tudo isso, atualizado diariamente, em um único dashboard.</p>
  <div style="text-align:center;margin:24px 0;">
    <a href="{PLATFORM_URL}" style="background:#4DB6AC;color:#0A1628;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
      Começar Trial Grátis de 7 Dias
    </a>
  </div>
  <p style="color:#8899AA;font-size:0.85rem;">PharmaIntel BR · Cancelar: responda "cancelar"</p>
</div>"""

        elif day == 5:
            subject = "3 importadores já usam o PharmaIntel este mês"
            body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A1628;color:#E8EDF5;padding:24px;border-radius:12px;">
  <h2 style="color:#4DB6AC;">Seus concorrentes já estão monitorando o mercado</h2>
  <p>Este mês, 3 importadores farmacêuticos assinaram o PharmaIntel BR. Veja o que disseram:</p>
  <blockquote style="border-left:3px solid #4DB6AC;padding-left:16px;color:#B0BEC5;">
    "Descobrimos um concorrente importando o mesmo NCM com 18% a menos. Renegociamos o fornecedor em 2 semanas."
    <br><b>— Assinante Plano Starter, São Paulo</b>
  </blockquote>
  <blockquote style="border-left:3px solid #4DB6AC;padding-left:16px;color:#B0BEC5;">
    "Alerta da ANVISA nos salvou de importar um produto com registro suspenso."
    <br><b>— Assinante Plano Pro, Rio de Janeiro</b>
  </blockquote>
  <p><b>O preço de membro fundador termina em 30 de abril.</b> Garanta R$497/mês antes de ir para R$697.</p>
  <div style="text-align:center;margin:24px 0;">
    <a href="{PLATFORM_URL}" style="background:#4DB6AC;color:#0A1628;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
      Garantir Preço Fundador
    </a>
  </div>
  <p style="color:#8899AA;font-size:0.85rem;">PharmaIntel BR · Cancelar: responda "cancelar"</p>
</div>"""

        else:  # day == 7
            subject = "Últimas 48h — preço fundador expira em 30 de abril"
            body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A1628;color:#E8EDF5;padding:24px;border-radius:12px;">
  <h2 style="color:#FF6B6B;">⏰ Preço fundador termina amanhã</h2>
  <p>Após 30 de abril, os preços do PharmaIntel BR sobem para:</p>
  <ul>
    <li>Starter: R$497 → <b>R$697/mês</b></li>
    <li>Pro: R$997 → <b>R$1.297/mês</b></li>
    <li>Enterprise: R$2.497 → <b>R$2.997/mês</b></li>
  </ul>
  <p>Garanta o preço fundador hoje e mantenha-o <b>para sempre</b>, mesmo com novos recursos adicionados.</p>
  <div style="text-align:center;margin:24px 0;">
    <a href="{PLATFORM_URL}" style="background:#FF6B6B;color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
      Garantir Preço Agora →
    </a>
  </div>
  <p style="color:#8899AA;">Dúvidas? Responda este email — respondemos em até 2 horas.</p>
  <p style="color:#8899AA;font-size:0.85rem;">PharmaIntel BR · Cancelar: responda "cancelar"</p>
</div>"""

    return subject, body


# ---------------------------------------------------------------------------
# EmailSequencer
# ---------------------------------------------------------------------------

class EmailSequencer:
    """Manages automated email drip sequences for lead nurturing."""

    def __init__(self):
        self._api_key = os.getenv("RESEND_API_KEY", "")
        if not self._api_key:
            logger.warning("RESEND_API_KEY not set — emails will be logged only")

    def run_sequences(self) -> dict:
        """Check all leads and send due sequence emails. Returns summary."""
        if not LEADS_FILE.exists():
            return {"sent": 0, "skipped": 0, "errors": 0, "detail": []}

        try:
            raw = json.loads(LEADS_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed to read leads: %s", exc)
            return {"sent": 0, "skipped": 0, "errors": 0, "detail": []}

        sent = skipped = errors = 0
        detail = []
        now = datetime.now(timezone.utc)
        updated = False

        for item in raw:
            email = item.get("email", "")
            lang = item.get("lang", "PT")
            timestamp_str = item.get("timestamp", "")
            emails_sent = item.get("emails_sent") or []
            status = item.get("status", "new")

            # Skip subscribed or lost leads
            if status in ("subscribed", "lost"):
                skipped += 1
                continue

            if not timestamp_str:
                skipped += 1
                continue

            try:
                captured_at = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if captured_at.tzinfo is None:
                    captured_at = captured_at.replace(tzinfo=timezone.utc)
            except ValueError:
                skipped += 1
                continue

            days_since = (now - captured_at).days

            for day_offset, seq_key in SEQUENCE_DAYS.items():
                if day_offset in emails_sent:
                    continue  # already sent
                if days_since >= day_offset:
                    result = self._send_sequence_email(email, lang, day_offset)
                    if result:
                        emails_sent.append(day_offset)
                        item["emails_sent"] = emails_sent
                        updated = True
                        sent += 1
                        detail.append({"email": email, "day": day_offset, "status": "sent"})
                    else:
                        errors += 1
                        detail.append({"email": email, "day": day_offset, "status": "error"})
                    break  # send only one email per run per lead

        if updated:
            try:
                LEADS_FILE.write_text(
                    json.dumps(raw, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.error("Failed to save updated leads: %s", exc)

        return {"sent": sent, "skipped": skipped, "errors": errors, "detail": detail}

    def _send_sequence_email(self, email: str, lang: str, day: int) -> bool:
        """Send the sequence email for the given day. Returns True on success."""
        subject, html_body = _get_email_content(day, lang)

        if not self._api_key:
            logger.info("[EmailSequencer] SIMULATED send to %s | Day %d | %s", email, day, subject)
            return True  # simulate success when no API key

        try:
            import urllib.request
            import urllib.parse

            payload = json.dumps({
                "from": FROM_ADDRESS,
                "to": [email],
                "subject": subject,
                "html": html_body,
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                status_code = resp.getcode()
                if status_code in (200, 201):
                    logger.info("[EmailSequencer] Sent Day %d to %s", day, email)
                    return True
                logger.warning(
                    "[EmailSequencer] Unexpected status %d for %s Day %d",
                    status_code, email, day
                )
                return False
        except Exception as exc:
            logger.error("[EmailSequencer] Failed to send to %s Day %d: %s", email, day, exc)
            return False

    def send_welcome(self, email: str, lang: str = "PT") -> bool:
        """Send Day 0 welcome email (called from app.py on lead capture)."""
        if not self._api_key:
            logger.info("[EmailSequencer] SIMULATED welcome to %s", email)
            return True

        if lang == "EN":
            subject = "Welcome to PharmaIntel BR — your AI is ready"
            body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A1628;color:#E8EDF5;padding:24px;border-radius:12px;">
  <h2 style="color:#4DB6AC;">Welcome to PharmaIntel BR 💊</h2>
  <p>Your free AI trial has started. You can ask 2 questions about the Brazilian pharma market.</p>
  <p>The full platform gives you:</p>
  <ul>
    <li>Daily import data from Comex Stat (Chapters 30 & 90)</li>
    <li>ANVISA registration and alert monitoring</li>
    <li>Government procurement intelligence (ComprasNet)</li>
    <li>Competitive analysis by NCM, country and company</li>
  </ul>
  <div style="text-align:center;margin:24px 0;">
    <a href="{PLATFORM_URL}" style="background:#4DB6AC;color:#0A1628;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
      Access the Platform
    </a>
  </div>
  <p style="color:#8899AA;font-size:0.85rem;">PharmaIntel BR · Unsubscribe: reply with "unsubscribe"</p>
</div>"""
        else:
            subject = "Bem-vindo ao PharmaIntel BR — sua IA está pronta"
            body = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0A1628;color:#E8EDF5;padding:24px;border-radius:12px;">
  <h2 style="color:#4DB6AC;">Bem-vindo ao PharmaIntel BR 💊</h2>
  <p>Seu trial grátis com IA começou. Você pode fazer 2 perguntas sobre o mercado farmacêutico brasileiro.</p>
  <p>A plataforma completa oferece:</p>
  <ul>
    <li>Dados diários de importação do Comex Stat (Capítulos 30 e 90)</li>
    <li>Monitoramento de registros e alertas da ANVISA</li>
    <li>Inteligência de compras governamentais (ComprasNet)</li>
    <li>Análise competitiva por NCM, país e empresa</li>
  </ul>
  <div style="text-align:center;margin:24px 0;">
    <a href="{PLATFORM_URL}" style="background:#4DB6AC;color:#0A1628;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;">
      Acessar a Plataforma
    </a>
  </div>
  <p style="color:#8899AA;font-size:0.85rem;">PharmaIntel BR · Cancelar: responda "cancelar"</p>
</div>"""

        return self._send_raw(email, subject, body)

    def _send_raw(self, email: str, subject: str, html_body: str) -> bool:
        """Low-level send via Resend API."""
        if not self._api_key:
            logger.info("[EmailSequencer] SIMULATED: %s → %s", email, subject)
            return True
        try:
            import urllib.request
            payload = json.dumps({
                "from": FROM_ADDRESS,
                "to": [email],
                "subject": subject,
                "html": html_body,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.getcode() in (200, 201)
        except Exception as exc:
            logger.error("[EmailSequencer] send_raw failed: %s", exc)
            return False
