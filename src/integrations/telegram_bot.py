"""
telegram_bot.py
===============
PharmaIntel BR — Telegram Bot Integration.

Allows subscribers to interact with the AI agent via Telegram.
Uses polling (no webhook needed for Render).

Run as background thread from app.py.
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


def _api(token: str, method: str, **kwargs) -> dict:
    url = TELEGRAM_API.format(token=token, method=method)
    try:
        resp = requests.post(url, json=kwargs, timeout=15)
        return resp.json()
    except Exception as exc:
        logger.warning("Telegram API error: %s", exc)
        return {}


def send_message(token: str, chat_id: int, text: str) -> None:
    _api(token, "sendMessage", chat_id=chat_id, text=text, parse_mode="Markdown")


def _handle_message(token: str, message: dict) -> None:
    chat_id = message.get("chat", {}).get("id")
    text    = message.get("text", "").strip()
    user    = message.get("from", {}).get("first_name", "")

    if not chat_id or not text:
        return

    # Commands
    if text.startswith("/start"):
        send_message(token, chat_id, (
            f"👋 Olá {user}! Bem-vindo ao *PharmaIntel AI*.\n\n"
            "💊 Sou a IA de inteligência do mercado farmacêutico brasileiro.\n\n"
            "Pergunte qualquer coisa sobre importações, ANVISA, preços de compras públicas ou oportunidades de mercado.\n\n"
            "_Exemplo: Quais os maiores importadores de insulina no Brasil?_"
        ))
        return

    if text.startswith("/help"):
        send_message(token, chat_id, (
            "*PharmaIntel AI — Comandos*\n\n"
            "/start — Bem-vindo\n"
            "/help — Ajuda\n\n"
            "Ou simplesmente faça sua pergunta diretamente!\n\n"
            "_Exemplos:_\n"
            "• Quais empresas importaram soro fisiológico em 2025?\n"
            "• Qual o preço médio de insulina nas licitações?\n"
            "• Há oportunidades de biossimilares vencendo patente?"
        ))
        return

    # AI response
    send_message(token, chat_id, "⏳ Consultando dados farmacêuticos...")

    try:
        from src.agents.pharma_agent import PharmaAgent
        agent = PharmaAgent(year=2025)
        response = agent.chat(
            message=text,
            user_plan="starter",
            lang="PT",
        )
        answer = response.text or "Não foi possível processar sua pergunta. Tente novamente."
    except Exception as exc:
        logger.error("Telegram AI error: %s", exc)
        answer = "❌ Erro ao consultar a IA. Tente novamente em instantes."

    send_message(token, chat_id, answer)


def _polling_loop(token: str) -> None:
    """Long-polling loop — runs forever in background thread."""
    offset = 0
    logger.info("Telegram bot polling started")

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
    """Start the Telegram bot in a background thread. Returns thread or None."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return None

    t = threading.Thread(target=_polling_loop, args=(token,), daemon=True)
    t.start()
    logger.info("Telegram bot started")
    return t
