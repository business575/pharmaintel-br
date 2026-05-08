"""
inbox_agent.py — PharmaIntel BR Inbox Monitor Agent

Roda a cada hora via Railway Cron ou manualmente.
- Le emails nao lidos do business@globalhealthcareaccess.com
- Classifica: interesse / pergunta / bounce / auto-reply / unsubscribe
- Responde automaticamente leads com interesse
- Atualiza status no banco de dados
- Loga tudo para revisao
"""

from __future__ import annotations

import imaplib
import email as emaillib
import json
import logging
import os
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT         = Path(__file__).resolve().parents[2]
LOG_FILE     = ROOT / "data" / "exports" / "inbox_agent_log.json"
GMAIL_USER   = os.getenv("GMAIL_USER", "")
GMAIL_PASS   = os.getenv("GMAIL_APP_PASSWORD", "")
GROQ_KEY     = os.getenv("GROQ_API_KEY", "")
TOUR_URL     = "https://business575.github.io/pharmaintel-br"
CALENDLY_URL = "https://calendly.com/vinicius-hospitalar/30min"
PLATFORM_URL = "https://pharmaintel-br.onrender.com"

# Dominios/emails a ignorar (bounce, spam, newsletters)
SKIP_SENDERS = [
    "mailer-daemon", "postmaster", "noreply", "no-reply",
    "newsletter", "unsubscribe", "bounce", "notification",
    "marketing", "promo", "campaign", "digest", "weekly", "daily",
    "alerts@", "updates@", "news@", "info@stripe", "hello@render",
    "wix.com", "uptimerobot", "github.com", "railway.app",
    "empiricus", "cyberman", "cafecomceo", "fiercepharma",
    "govdelivery", "senseonics", "websummit", "airtable",
    "formspree", "n8n.io", "sbpc", "jota.info", "alibaba",
    "bradesco", "vivo.com", "accor.com", "amazon.com",
    "biopharmguy", "singularity-group", "textbroker", "mailchi",
    "beehiiv", "substack", "hubspot", "mailchimp", "klaviyo",
    "vinicius.hospitalar@gmail.com",
]

# So responde emails de dominios de prospects conhecidos
PROSPECT_DOMAINS_ONLY = True  # Se True, ignora emails fora do pipeline

# Palavras que indicam interesse genuino
INTEREST_KEYWORDS = [
    "interessado", "interested", "demo", "apresentacao", "apresentação",
    "reuniao", "reunião", "meeting", "call", "conversa", "agendar",
    "schedule", "quando", "when", "quero saber", "want to know",
    "proposta", "proposal", "preco", "preco", "price", "plano", "plan",
    "contrato", "contract", "assinar", "subscribe", "comprar", "buy",
    "trial", "teste", "access", "acesso", "cadastro", "register",
    "sim", "yes", "claro", "of course", "sure", "absolutely",
    "obrigado pelo contato", "thank you for reaching out",
]

# Palavras que indicam desinteresse
UNSUBSCRIBE_KEYWORDS = [
    "cancelar", "unsubscribe", "remover", "remove", "nao tenho interesse",
    "not interested", "stop", "parar", "descadastrar",
]


# ---------------------------------------------------------------------------
# Gmail IMAP
# ---------------------------------------------------------------------------

def _get_mail_client() -> Optional[imaplib.IMAP4_SSL]:
    if not GMAIL_USER or not GMAIL_PASS:
        logger.error("GMAIL_USER ou GMAIL_APP_PASSWORD nao configurado")
        return None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        return mail
    except Exception as e:
        logger.error("Erro ao conectar ao Gmail IMAP: %s", e)
        return None


def _get_body(msg) -> str:
    """Extrai texto puro do email."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            pass
    return body[:2000]


def _get_prospect_emails() -> set:
    """Retorna set de emails de prospects no banco."""
    try:
        from src.db.database import get_prospects, init_db
        init_db()
        return {p["email"].lower() for p in get_prospects(limit=500) if p["email"]}
    except Exception:
        return set()


def _is_skip(sender: str, subject: str) -> bool:
    s = (sender + subject).lower()
    if any(kw in s for kw in SKIP_SENDERS):
        return True
    return False


def _is_known_prospect(sender_email: str, prospect_emails: set) -> bool:
    """Verifica se o remetente e um prospect conhecido."""
    if not PROSPECT_DOMAINS_ONLY:
        return True
    # Verifica email exato ou dominio
    domain = sender_email.split("@")[-1] if "@" in sender_email else ""
    return (sender_email in prospect_emails or
            any(domain in pe for pe in prospect_emails))


def _is_auto_reply(body: str, subject: str) -> bool:
    s = (body + subject).lower()
    markers = ["auto reply", "auto-reply", "automatic reply", "out of office",
                "ausente", "fora do escritorio", "foi recebido", "was received",
                "esta mensagem e automatica", "this is an automated"]
    return any(m in s for m in markers)


def _classify(body: str, subject: str) -> str:
    """Classifica o email: interesse / pergunta / unsubscribe / auto_reply / outros"""
    text = (body + " " + subject).lower()

    if _is_auto_reply(body, subject):
        return "auto_reply"

    if any(kw in text for kw in UNSUBSCRIBE_KEYWORDS):
        return "unsubscribe"

    if any(kw in text for kw in INTEREST_KEYWORDS):
        return "interesse"

    # Perguntas sobre o produto
    if "?" in body or any(kw in text for kw in ["o que", "como", "what", "how", "can you", "voce pode"]):
        return "pergunta"

    return "outros"


# ---------------------------------------------------------------------------
# Groq — gera resposta personalizada
# ---------------------------------------------------------------------------

def _generate_response(sender_name: str, company: str, body: str,
                        classification: str, lang: str = "PT") -> str:
    """Usa Groq/Llama para gerar resposta personalizada."""
    if not GROQ_KEY:
        return _fallback_response(classification, lang)

    if lang == "EN":
        prompt = f"""You are the CEO of PharmaIntel BR, a Brazilian pharma market intelligence platform.
A prospect from {company} ({sender_name}) replied to your outreach email with:

"{body[:500]}"

Their message is classified as: {classification}

Write a SHORT, professional reply in English (max 4 sentences):
- If "interesse": confirm their interest, propose a 30-min demo, share the Calendly link
- If "pergunta": answer briefly and invite them to a demo
- Do NOT use generic phrases. Be direct and specific about PharmaIntel BR.
- End with: Book a demo: {CALENDLY_URL}
- Sign as: Vinicius Figueiredo | CEO PharmaIntel BR"""
    else:
        prompt = f"""Voce e o CEO da PharmaIntel BR, plataforma de inteligencia de mercado farmaceutico brasileiro.
Um prospect da {company} ({sender_name}) respondeu seu email de prospecao com:

"{body[:500]}"

A mensagem e classificada como: {classification}

Escreva uma resposta CURTA e profissional em portugues (max 4 frases):
- Se "interesse": confirme o interesse, proponha uma demo de 30 min, compartilhe o Calendly
- Se "pergunta": responda brevemente e convide para uma demo
- NAO use frases genericas. Seja direto sobre o PharmaIntel BR.
- Termine com: Agendar: {CALENDLY_URL}
- Assine como: Vinicius Figueiredo | CEO PharmaIntel BR"""

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_KEY)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=200,
            temperature=0.5,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("Groq error: %s", e)
        return _fallback_response(classification, lang)


def _fallback_response(classification: str, lang: str) -> str:
    if lang == "EN":
        return (
            f"Thank you for your reply! I'd love to show you PharmaIntel BR in action — "
            f"it only takes 30 minutes to see exactly what the platform can do for your company. "
            f"Book a time here: {CALENDLY_URL}\n\nBest,\nVinicius Figueiredo | CEO PharmaIntel BR"
        )
    return (
        f"Obrigado pelo retorno! Seria otimo mostrar o PharmaIntel BR ao vivo para voce — "
        f"30 minutos para ver exatamente o que a plataforma entrega para o seu perfil. "
        f"Agendar: {CALENDLY_URL}\n\nAtenciosamente,\nVinicius Figueiredo | CEO PharmaIntel BR"
    )


# ---------------------------------------------------------------------------
# Envia resposta via SMTP
# ---------------------------------------------------------------------------

def _send_reply(to_email: str, subject: str, body_text: str,
                reply_to_msg_id: str = "") -> bool:
    if not GMAIL_USER or not GMAIL_PASS:
        return False
    try:
        html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;">
<div style="background:#0A1628;padding:20px;border-radius:8px 8px 0 0;">
<h2 style="color:#4DB6AC;margin:0;">PharmaIntel BR</h2>
</div>
<div style="background:#fff;padding:24px;border:1px solid #e0e0e0;">
{body_text.replace(chr(10), '<br>')}
<div style="text-align:center;margin:20px 0;">
<a href="{CALENDLY_URL}" style="background:#4DB6AC;color:#fff;padding:12px 24px;
   border-radius:6px;text-decoration:none;font-weight:700;">
Agendar Demo →
</a>
</div>
<hr style="border:none;border-top:1px solid #eee;margin:16px 0;">
<p style="color:#888;font-size:12px;">
<strong>Vinicius Figueiredo</strong> · CEO PharmaIntel BR<br>
business@globalhealthcareaccess.com · +55-21-97282-9820<br>
<a href="{PLATFORM_URL}" style="color:#4DB6AC;">{PLATFORM_URL}</a>
</p>
</div></div>"""

        msg = MIMEMultipart("alternative")
        msg["From"]    = f"Vinicius Figueiredo | PharmaIntel BR <{GMAIL_USER}>"
        msg["To"]      = to_email
        msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
        msg["Reply-To"] = GMAIL_USER
        if reply_to_msg_id:
            msg["In-Reply-To"] = reply_to_msg_id
            msg["References"]  = reply_to_msg_id
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        logger.error("Erro ao enviar resposta: %s", e)
        return False


# ---------------------------------------------------------------------------
# Atualiza banco de dados
# ---------------------------------------------------------------------------

def _update_prospect_status(email: str, status: str, notes: str = "") -> None:
    try:
        from src.db.models import Prospect
        from src.db.database import SessionLocal, init_db
        init_db()
        with SessionLocal() as s:
            p = s.query(Prospect).filter(
                Prospect.email == email.lower()
            ).first()
            if p:
                p.status = status
                p.notes  = (p.notes or "") + f" | {notes}"
                p.last_contact = datetime.now(timezone.utc)
                s.commit()
    except Exception as e:
        logger.warning("DB update error: %s", e)


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

def _log(entry: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logs = []
    if LOG_FILE.exists():
        try:
            logs = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            logs = []
    logs.append(entry)
    LOG_FILE.write_text(json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main — scan e acao
# ---------------------------------------------------------------------------

def run_inbox_scan(auto_reply: bool = True, dry_run: bool = False) -> dict:
    """
    Escaneia inbox, classifica emails e responde automaticamente.
    dry_run=True: classifica mas nao envia respostas.
    """
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scanned": 0,
        "interesse": 0,
        "perguntas": 0,
        "auto_replies": 0,
        "unsubscribes": 0,
        "respostas_enviadas": 0,
        "detalhes": [],
    }

    mail = _get_mail_client()
    if not mail:
        return report

    prospect_emails = _get_prospect_emails()
    logger.info("Prospects no banco: %d", len(prospect_emails))

    try:
        mail.select("INBOX")
        _, msgs = mail.search(None, "UNSEEN")
        ids = msgs[0].split()
        logger.info("Inbox scan: %d emails nao lidos", len(ids))

        for num in ids:
            try:
                _, data = mail.fetch(num, "(RFC822)")
                msg = emaillib.message_from_bytes(data[0][1])
                sender  = msg.get("From", "")
                subject = msg.get("Subject", "")
                msg_id  = msg.get("Message-ID", "")
                date    = msg.get("Date", "")

                # Extrai email puro do sender
                import re
                email_match = re.search(r'[\w\.\-]+@[\w\.\-]+\.[a-zA-Z]{2,}', sender)
                sender_email = email_match.group(0).lower() if email_match else ""
                sender_name  = sender.split("<")[0].strip().strip('"') if "<" in sender else sender_email

                if _is_skip(sender, subject):
                    continue

                if not _is_known_prospect(sender_email, prospect_emails):
                    logger.debug("Ignorando email de nao-prospect: %s", sender_email)
                    continue

                body = _get_body(msg)
                classification = _classify(body, subject)
                report["scanned"] += 1

                # Detecta idioma pela presenca de palavras portuguesas
                lang = "PT" if any(w in body.lower() for w in
                                   ["obrigado", "olá", "ola", "prezado", "bom dia",
                                    "boa tarde", "boa noite", "empresa", "produto"]) else "EN"

                # Extrai nome da empresa do email
                company = sender_email.split("@")[1].split(".")[0].title() if "@" in sender_email else "empresa"

                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "from": sender_email,
                    "sender_name": sender_name,
                    "company": company,
                    "subject": subject,
                    "date": date,
                    "classification": classification,
                    "lang": lang,
                    "body_preview": body[:200],
                    "responded": False,
                }

                logger.info("[%s] %s <%s>", classification.upper(), sender_name, sender_email)

                if classification == "interesse":
                    report["interesse"] += 1
                    _update_prospect_status(sender_email, "interested", "respondeu com interesse")

                    if auto_reply and not dry_run:
                        reply = _generate_response(sender_name, company, body, classification, lang)
                        ok = _send_reply(sender_email, subject, reply, msg_id)
                        if ok:
                            entry["responded"] = True
                            entry["reply_sent"] = reply[:200]
                            report["respostas_enviadas"] += 1
                            logger.info("  → Resposta enviada para %s", sender_email)

                elif classification == "pergunta":
                    report["perguntas"] += 1
                    _update_prospect_status(sender_email, "engaged", "fez pergunta")

                    if auto_reply and not dry_run:
                        reply = _generate_response(sender_name, company, body, classification, lang)
                        ok = _send_reply(sender_email, subject, reply, msg_id)
                        if ok:
                            entry["responded"] = True
                            entry["reply_sent"] = reply[:200]
                            report["respostas_enviadas"] += 1

                elif classification == "auto_reply":
                    report["auto_replies"] += 1
                    # Confirma que o email chegou — atualiza para 'delivered'
                    _update_prospect_status(sender_email, "contacted", "auto-reply recebido — email valido")

                elif classification == "unsubscribe":
                    report["unsubscribes"] += 1
                    _update_prospect_status(sender_email, "unsubscribed", "pediu para remover")

                _log(entry)
                report["detalhes"].append(entry)

            except Exception as e:
                logger.warning("Erro ao processar email %s: %s", num, e)

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return report


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    dry = "--dry-run" in sys.argv
    result = run_inbox_scan(auto_reply=True, dry_run=dry)
    print(json.dumps(result, indent=2, ensure_ascii=False))
