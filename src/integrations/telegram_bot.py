"""
telegram_bot.py
===============
PharmaIntel BR — Agente de Vendas via Telegram.

Fluxo:
  1. Detecta idioma (PT/EN)
  2. Apresenta a plataforma
  3. Qualifica o lead (porte, produto, necessidade)
  4. Tenta fechar a venda (envia link + planos)
  5. Se não fechar → agenda reunião com Vinicius

Powered by Claude Opus 4.7 via Anthropic API.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

# Memória de conversa por chat_id
_conversations: dict[int, list[dict]] = {}
_user_lang: dict[int, str] = {}

PLATFORM_URL = "https://pharmaceuticaai.com"
BOOKING_URL  = "https://calendly.com/vinicius-hospitalar"  # ajuste se tiver Calendly
CONTACT_INFO = "vinicius.hospitalar@gmail.com | WhatsApp: +55 11 XXXXX-XXXX"

SYSTEM_PROMPT_PT = """Você é o PHD Intel.AI, agente de vendas da PharmaIntel BR — plataforma de inteligência de mercado farmacêutico brasileiro.

SEU OBJETIVO: Qualificar o lead, apresentar a plataforma e FECHAR A VENDA. Se não conseguir fechar, agendar uma reunião.

SOBRE A PLATAFORMA:
- Dados reais de importação farmacêutica (Comex Stat/MDIC)
- Monitoramento ANVISA — alertas, registros, vencimentos
- Preços de licitações públicas (ComprasNet/PNCP) e BPS
- Relatórios estratégicos em PDF gerados por IA (Opus 4.7)
- Monitoramento de patentes e oportunidades de biossimilares

PÚBLICO-ALVO: Importadores farmacêuticos brasileiros, hospitais, distribuidores, laboratórios

PLANOS:
- Starter R$ 497/mês — Dashboard completo, NCMs ilimitados, alertas ANVISA
- Pro R$ 997/mês — IA avançada, relatórios PDF, dados UN Comtrade, patentes
- Enterprise R$ 2.497/mês — Opus 4.7, precisão 99%, suporte dedicado

FLUXO DE VENDAS:
1. Cumprimente e pergunte sobre o negócio do lead
2. Identifique a dor (preços, concorrência, ANVISA, licitações)
3. Mostre como a plataforma resolve essa dor específica
4. Apresente o plano adequado e o preço
5. Peça para acessar: {url}
6. Se hesitar → ofereça reunião de demo de 20 minutos

REGRAS:
- Seja consultivo, não agressivo
- Use dados concretos para impressionar
- Máximo 3 parágrafos por mensagem — seja direto
- Se perguntar algo técnico fora do escopo, redirecione para a venda
- Sempre termine com uma pergunta ou chamada para ação
""".format(url=PLATFORM_URL)

SYSTEM_PROMPT_EN = """You are PHD Intel.AI, sales agent for PharmaIntel BR — Brazil's pharmaceutical market intelligence platform.

YOUR GOAL: Qualify the lead, present the platform and CLOSE THE SALE. If unable to close, schedule a meeting.

ABOUT THE PLATFORM:
- Real pharmaceutical import data (Comex Stat/MDIC — Brazil's official trade data)
- ANVISA monitoring — alerts, registrations, expiry dates
- Public procurement prices (ComprasNet/PNCP) and BPS government price database
- AI-generated strategic PDF reports (Opus 4.7)
- Patent monitoring and biosimilar opportunities

TARGET: Brazilian pharma importers, hospitals, distributors, laboratories, international companies seeking Brazilian partners

PLANS:
- Starter R$ 497/month — Full dashboard, unlimited NCMs, ANVISA alerts
- Pro R$ 997/month — Advanced AI, PDF reports, UN Comtrade data, patents
- Enterprise R$ 2,497/month — Opus 4.7, 99% accuracy, dedicated support

SALES FLOW:
1. Greet and ask about their business
2. Identify the pain (prices, competition, ANVISA, procurement)
3. Show how the platform solves that specific pain
4. Present the right plan and price
5. Ask them to access: {url}
6. If hesitant → offer a 20-minute demo meeting

RULES:
- Be consultive, not pushy
- Use concrete data to impress
- Max 3 paragraphs per message — be direct
- Always end with a question or call to action
""".format(url=PLATFORM_URL)


def _api(token: str, method: str, **kwargs) -> dict:
    url = TELEGRAM_API.format(token=token, method=method)
    try:
        resp = requests.post(url, json=kwargs, timeout=15)
        return resp.json()
    except Exception as exc:
        logger.warning("Telegram API error: %s", exc)
        return {}


def send_message(token: str, chat_id: int, text: str) -> None:
    # Telegram limita mensagens a 4096 chars
    if len(text) > 4000:
        text = text[:3997] + "..."
    _api(token, "sendMessage", chat_id=chat_id, text=text, parse_mode="Markdown")


def _detect_language(text: str) -> str:
    """Detecta idioma pelo primeiro contato."""
    english_words = ["hello", "hi", "hey", "good", "morning", "afternoon", "evening",
                     "what", "how", "where", "when", "who", "why", "please", "thank",
                     "interested", "platform", "price", "information"]
    text_lower = text.lower()
    if any(w in text_lower for w in english_words):
        return "EN"
    return "PT"


def _call_opus(messages: list[dict], lang: str) -> str:
    """Chama Claude Opus 4.7 via Anthropic API."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return _fallback_response(lang)

    system = SYSTEM_PROMPT_PT if lang == "PT" else SYSTEM_PROMPT_EN

    try:
        resp = requests.post(
            ANTHROPIC_API,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-opus-4-7",
                "max_tokens": 500,
                "system": system,
                "messages": messages,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("content", [{}])[0].get("text", "")
    except Exception as exc:
        logger.error("Opus API error: %s", exc)

    return _fallback_response(lang)


def _fallback_response(lang: str) -> str:
    if lang == "EN":
        return (
            "Thank you for your interest in *PharmaIntel BR*! 🚀\n\n"
            "We provide real-time pharmaceutical market intelligence for Brazil — "
            "import data, ANVISA alerts, government procurement prices, and AI-generated strategic reports.\n\n"
            f"👉 Try it now: {PLATFORM_URL}\n\n"
            "Would you like a 20-minute demo? Just say *yes* and I'll connect you with our team!"
        )
    return (
        "Obrigado pelo seu interesse na *PharmaIntel BR*! 🚀\n\n"
        "Somos a plataforma de inteligência de mercado farmacêutico brasileiro — "
        "dados de importação em tempo real, alertas ANVISA, preços de licitações e relatórios estratégicos em PDF gerados por IA.\n\n"
        f"👉 Acesse agora: {PLATFORM_URL}\n\n"
        "Quer uma demo de 20 minutos? É só dizer *sim* e te conecto com nossa equipe!"
    )


def _handle_message(token: str, message: dict) -> None:
    chat_id  = message.get("chat", {}).get("id")
    text     = message.get("text", "").strip()
    username = message.get("from", {}).get("first_name", "")

    if not chat_id or not text:
        return

    # ── Comandos especiais ────────────────────────────────────────────────────
    if text.startswith("/start"):
        _conversations[chat_id] = []
        lang = "PT"
        _user_lang[chat_id] = lang
        send_message(token, chat_id, (
            f"👋 Olá {username}! Bem-vindo à *PharmaIntel BR* — inteligência farmacêutica com IA.\n\n"
            "Sou o *PHD Intel.AI*, seu consultor de mercado farmacêutico brasileiro.\n\n"
            "Me conta: você trabalha com importação, distribuição ou é hospital/laboratório? "
            "O que está buscando resolver no seu negócio? 🎯"
        ))
        return

    if text.lower() in ["/start@pharmaintel_bot", "/help", "/ajuda"]:
        lang = _user_lang.get(chat_id, "PT")
        if lang == "EN":
            send_message(token, chat_id,
                "*PharmaIntel BR — Commands*\n\n"
                "/start — Start conversation\n"
                "/planos — View plans and prices\n"
                "/demo — Request a demo\n"
                "/reuniao — Schedule a meeting\n\n"
                f"Or just talk to me! I'm here to help. 💊"
            )
        else:
            send_message(token, chat_id,
                "*PharmaIntel BR — Comandos*\n\n"
                "/start — Iniciar conversa\n"
                "/planos — Ver planos e preços\n"
                "/demo — Solicitar demo\n"
                "/reuniao — Agendar reunião\n\n"
                "Ou simplesmente fale comigo! Estou aqui para ajudar. 💊"
            )
        return

    if text.startswith("/planos"):
        lang = _user_lang.get(chat_id, "PT")
        if lang == "EN":
            send_message(token, chat_id,
                "*PharmaIntel BR — Plans*\n\n"
                "🥉 *Starter — R$ 497/month*\n"
                "Full dashboard, unlimited NCMs, ANVISA alerts, real import data\n\n"
                "🥈 *Pro — R$ 997/month*\n"
                "Everything in Starter + Advanced AI, PDF reports, UN Comtrade, patents\n\n"
                "🥇 *Enterprise — R$ 2,497/month*\n"
                "Claude Opus 4.7, 99% accuracy, unlimited reports, dedicated support\n\n"
                f"👉 Try it now: {PLATFORM_URL}\n\n"
                "Which plan fits your needs best?"
            )
        else:
            send_message(token, chat_id,
                "*PharmaIntel BR — Planos*\n\n"
                "🥉 *Starter — R$ 497/mês*\n"
                "Dashboard completo, NCMs ilimitados, alertas ANVISA, dados reais de importação\n\n"
                "🥈 *Pro — R$ 997/mês*\n"
                "Tudo do Starter + IA avançada, relatórios PDF, UN Comtrade, patentes\n\n"
                "🥇 *Enterprise — R$ 2.497/mês*\n"
                "Claude Opus 4.7, precisão 99%, relatórios ilimitados, suporte dedicado\n\n"
                f"👉 Acesse agora: {PLATFORM_URL}\n\n"
                "Qual plano faz mais sentido para o seu negócio?"
            )
        return

    if text.startswith("/demo"):
        lang = _user_lang.get(chat_id, "PT")
        if lang == "EN":
            send_message(token, chat_id,
                "🎯 *Request a Demo*\n\n"
                f"Access the platform now: {PLATFORM_URL}\n"
                "Login: `admin` | Password: `pharmaintel2024`\n\n"
                "Or schedule a 20-minute live demo with our team:\n"
                f"📅 {BOOKING_URL}\n\n"
                "What product or molecule would you like to analyze in the demo?"
            )
        else:
            send_message(token, chat_id,
                "🎯 *Solicitar Demo*\n\n"
                f"Acesse a plataforma agora: {PLATFORM_URL}\n"
                "Login: `admin` | Senha: `pharmaintel2024`\n\n"
                "Ou agende uma demo ao vivo de 20 minutos com nossa equipe:\n"
                f"📅 {BOOKING_URL}\n\n"
                "Qual produto ou molécula você gostaria de analisar na demo?"
            )
        return

    if text.startswith("/reuniao") or text.startswith("/meeting"):
        lang = _user_lang.get(chat_id, "PT")
        if lang == "EN":
            send_message(token, chat_id,
                "📅 *Schedule a Meeting*\n\n"
                "I'll connect you directly with Vinicius, founder of PharmaIntel BR.\n\n"
                f"📧 Email: {CONTACT_INFO}\n"
                f"🔗 Calendar: {BOOKING_URL}\n\n"
                "Tell me: what's the best time for you and what topics should we cover?"
            )
        else:
            send_message(token, chat_id,
                "📅 *Agendar Reunião*\n\n"
                "Vou te conectar diretamente com o Vinicius, fundador da PharmaIntel BR.\n\n"
                f"📧 Contato: {CONTACT_INFO}\n"
                f"🔗 Agenda: {BOOKING_URL}\n\n"
                "Me diz: qual o melhor horário para você e quais tópicos quer cobrir?"
            )
        return

    # ── Conversa com IA ───────────────────────────────────────────────────────
    # Detecta idioma no primeiro contato
    if chat_id not in _user_lang:
        _user_lang[chat_id] = _detect_language(text)

    lang = _user_lang.get(chat_id, "PT")

    # Inicializa histórico
    if chat_id not in _conversations:
        _conversations[chat_id] = []

    # Adiciona mensagem do usuário
    _conversations[chat_id].append({"role": "user", "content": text})

    # Limita histórico a 20 mensagens para não explodir tokens
    if len(_conversations[chat_id]) > 20:
        _conversations[chat_id] = _conversations[chat_id][-20:]

    # Indicador de digitação
    _api(token, "sendChatAction", chat_id=chat_id, action="typing")

    # Chama Opus 4.7
    response = _call_opus(_conversations[chat_id], lang)

    # Adiciona resposta ao histórico
    _conversations[chat_id].append({"role": "assistant", "content": response})

    send_message(token, chat_id, response)


def _polling_loop(token: str) -> None:
    """Long-polling loop — roda forever em background thread."""
    offset = 0
    logger.info("Telegram sales agent polling started")

    while True:
        try:
            result = _api(token, "getUpdates", offset=offset, timeout=30, allowed_updates=["message"])
            updates = result.get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message")
                if message:
                    threading.Thread(
                        target=_handle_message,
                        args=(token, message),
                        daemon=True,
                    ).start()
        except Exception as exc:
            logger.warning("Telegram polling error: %s", exc)
            time.sleep(5)


def start_bot() -> Optional[threading.Thread]:
    """Inicia o agente de vendas em background thread."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN not set — sales agent disabled")
        return None

    t = threading.Thread(target=_polling_loop, args=(token,), daemon=True)
    t.start()
    logger.info("Telegram sales agent started (PHD Intel.AI)")
    return t
