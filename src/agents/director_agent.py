"""
director_agent.py - PharmaIntel AI Sales Director

Strategic AI that manages leads, sales pipeline and drives to R$50k goal.
Uses Claude Sonnet with tool calling to analyze pipeline and draft messages.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import anthropic as _anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    _anthropic = None  # type: ignore

try:
    from groq import Groq as _Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    _Groq = None  # type: ignore

PLAN_PRICES = {"starter": 497, "pro": 997, "enterprise": 2497}
GOAL = 50_000.0
END_DATE = "2026-04-30"

_SYSTEM_PT = """Você é a Diretora de Vendas IA da PharmaIntel BR — uma plataforma SaaS B2B de inteligência de mercado farmacêutico brasileiro.

Sua missão é alcançar R$50.000 em receita até 30 de abril de 2026. Hoje estamos na sprint final.

CONTEXTO DO PRODUTO:
PharmaIntel BR integra dados de Comex Stat, ANVISA, BPS e ComprasNet para importadores farmacêuticos.

PLANOS:
- Starter: R$497/mês — Dashboard básico, 3 NCMs monitorados
- Pro: R$997/mês — Todos NCMs, alertas ANVISA, ComprasNet
- Enterprise: R$2.497/mês — API access, white-label, suporte dedicado
- (Internacional) Starter: US$299 | Pro: US$499 | Enterprise: US$1.499

PÚBLICO: 8.500+ importadores ativos no Brasil + pipeline global de prospects internacionais.

SUAS RESPONSABILIDADES:
1. PIPELINE DE DEMOS — Analisar leads que testaram a IA, priorizar follow-ups, rascunhar mensagens WhatsApp/email
2. PIPELINE DE OUTREACH — Gerenciar a lista de prospects (Brasil + internacional), acionar envio de emails frios, monitorar status (pendente → contatado → convertido)
3. ESTRATÉGIA — Calcular projeções de receita, sugerir ações de maior impacto, criar propostas e scripts de vendas

FERRAMENTAS DISPONÍVEIS:
- get_pipeline / get_hot_leads / get_daily_target / get_revenue_progress → dados do pipeline de demos
- draft_whatsapp_message / draft_email_followup → rascunhos personalizados
- suggest_next_actions → sugestões estratégicas
- get_prospects → lista de prospects de outreach (status: pending/contacted/converted/all)
- run_outreach → acionar envio diário de emails frios (até 20/dia)
- get_outreach_stats → estatísticas do pipeline de outreach

Seja direta, estratégica e orientada a resultados. Use dados reais do pipeline quando disponível.
Responda em português do Brasil a menos que o usuário escreva em inglês."""

_SYSTEM_EN = """You are the AI Sales Director of PharmaIntel BR — a B2B SaaS platform for Brazilian pharmaceutical market intelligence.

Your mission is to reach R$50,000 in revenue by April 30, 2026. We're in the final sprint.

PRODUCT CONTEXT:
PharmaIntel BR integrates Comex Stat, ANVISA, BPS and ComprasNet data for pharmaceutical importers.

PLANS:
- Starter: R$497/month — Basic dashboard, 3 NCMs monitored
- Pro: R$997/month — All NCMs, ANVISA alerts, ComprasNet
- Enterprise: R$2,497/month — API access, white-label, dedicated support
- (International) Starter: US$299 | Pro: US$499 | Enterprise: US$1,499

AUDIENCE: 8,500+ active importers in Brazil + global pipeline of international prospects.

YOUR RESPONSIBILITIES:
1. DEMO PIPELINE — Analyze leads who tested the AI, prioritize follow-ups, draft WhatsApp/email messages
2. OUTREACH PIPELINE — Manage the prospect list (Brazil + international), trigger cold email sends, track status (pending → contacted → converted)
3. STRATEGY — Calculate revenue projections, suggest highest-impact actions, create proposals and sales scripts

AVAILABLE TOOLS:
- get_pipeline / get_hot_leads / get_daily_target / get_revenue_progress → demo pipeline data
- draft_whatsapp_message / draft_email_followup → personalized drafts
- suggest_next_actions → strategic suggestions
- get_prospects → outreach prospect list (status: pending/contacted/converted/all)
- run_outreach → trigger daily cold email send (up to 20/day)
- get_outreach_stats → outreach pipeline statistics

Be direct, strategic and results-oriented. Use real pipeline data when available."""


def _get_lead_manager():
    """Lazy import to avoid circular deps."""
    from src.crm.lead_manager import LeadManager
    return LeadManager()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tool_get_pipeline() -> dict:
    """Fetch current pipeline statistics."""
    try:
        lm = _get_lead_manager()
        return lm.get_pipeline_stats()
    except Exception as exc:
        return {"error": str(exc)}


def _tool_get_hot_leads() -> list[dict]:
    """Fetch leads most likely to convert."""
    try:
        lm = _get_lead_manager()
        hot = lm.get_hot_leads()
        return [
            {
                "email": l.email,
                "temperature": l.temperature,
                "questions_asked": l.questions_asked,
                "status": l.status,
                "lang": l.lang,
                "country_hint": l.country_hint,
                "timestamp": l.timestamp,
                "last_contact": l.last_contact,
                "notes": l.notes,
            }
            for l in hot[:10]
        ]
    except Exception as exc:
        return [{"error": str(exc)}]


def _tool_draft_whatsapp(email: str, lang: str = "PT") -> str:
    """Draft a personalized WhatsApp message for a lead."""
    try:
        lm = _get_lead_manager()
        leads = {l.email.lower(): l for l in lm.get_all_leads()}
        lead = leads.get(email.lower())
        q = lead.questions_asked if lead else 0
        temp = lead.temperature if lead else "cold"
    except Exception:
        q, temp, lead = 0, "cold", None

    if lang == "EN":
        if temp == "hot":
            return (
                f"Hi! I noticed you explored PharmaIntel BR twice already 🔥 "
                f"You're clearly interested in pharma market intelligence. "
                f"I'd love to show you how we're helping importers find opportunities "
                f"they didn't know existed. Can we chat for 15 min? "
                f"👉 https://pharmaintel-br.onrender.com"
            )
        return (
            f"Hi! You tried PharmaIntel BR's AI — did it help? "
            f"We have real import data, ANVISA alerts and competitive intel. "
            f"First month 20% off with code FOUNDER. "
            f"👉 https://pharmaintel-br.onrender.com"
        )
    else:
        if temp == "hot":
            return (
                f"Olá! Vi que você explorou o PharmaIntel BR mais de uma vez 🔥 "
                f"Você claramente tem interesse em inteligência de mercado farmacêutico. "
                f"Adoraria mostrar como estamos ajudando importadores a encontrar "
                f"oportunidades que não sabiam que existiam. Podemos conversar 15 min? "
                f"👉 https://pharmaintel-br.onrender.com"
            )
        return (
            f"Olá! Você testou a IA do PharmaIntel BR — gostou? "
            f"Temos dados reais de importação, alertas ANVISA e inteligência competitiva. "
            f"Primeiro mês com 20% de desconto com o código FOUNDER. "
            f"👉 https://pharmaintel-br.onrender.com"
        )


def _tool_draft_email(email: str, lang: str = "PT") -> str:
    """Draft a personalized follow-up email for a lead."""
    try:
        lm = _get_lead_manager()
        leads = {l.email.lower(): l for l in lm.get_all_leads()}
        lead = leads.get(email.lower())
        temp = lead.temperature if lead else "cold"
    except Exception:
        temp, lead = "cold", None

    if lang == "EN":
        subject = "Your pharma market intelligence is ready"
        body = (
            f"Hi,\n\nYou tried PharmaIntel BR's AI recently.\n\n"
            f"Here's what our platform can show you right now:\n"
            f"• Which competitors are importing your NCMs and at what price\n"
            f"• ANVISA registration status for 40,000+ products\n"
            f"• Government procurement opportunities (ComprasNet)\n"
            f"• Real-time import trends by NCM, country and company\n\n"
            f"{'You tested our AI twice — you clearly see the value.' if temp == 'hot' else 'One AI question gave you a taste — imagine full access.'}\n\n"
            f"Start your 7-day free trial: https://pharmaintel-br.onrender.com\n\n"
            f"Best,\nPharmaIntel BR Team"
        )
    else:
        subject = "Sua inteligência de mercado farmacêutico está pronta"
        body = (
            f"Olá,\n\nVocê testou a IA do PharmaIntel BR recentemente.\n\n"
            f"Veja o que nossa plataforma pode mostrar agora:\n"
            f"• Quais concorrentes importam seus NCMs e a que preço\n"
            f"• Status de registro ANVISA de 40.000+ produtos\n"
            f"• Oportunidades em licitações (ComprasNet)\n"
            f"• Tendências de importação em tempo real por NCM, país e empresa\n\n"
            f"{'Você testou nossa IA duas vezes — claramente vê o valor.' if temp == 'hot' else 'Uma pergunta à IA deu um gostinho — imagine o acesso completo.'}\n\n"
            f"Comece seu trial gratuito de 7 dias: https://pharmaintel-br.onrender.com\n\n"
            f"Atenciosamente,\nEquipe PharmaIntel BR"
        )
    return f"Assunto: {subject}\n\n{body}"


def _tool_get_daily_target() -> dict:
    """How many sales are needed per day to hit the R$50k goal."""
    try:
        lm = _get_lead_manager()
        return lm.get_days_to_goal()
    except Exception as exc:
        return {"error": str(exc)}


def _tool_get_revenue_progress() -> dict:
    """Current vs target revenue."""
    try:
        lm = _get_lead_manager()
        rev = lm.get_revenue_actual()
        remaining = max(GOAL - rev, 0)
        pct = min((rev / GOAL) * 100, 100)
        return {
            "goal": GOAL,
            "revenue_actual": rev,
            "remaining": remaining,
            "pct_complete": round(pct, 1),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_suggest_next_actions(lang: str = "PT") -> list[str]:
    """Suggest the 3 most impactful actions right now."""
    try:
        lm = _get_lead_manager()
        hot = lm.get_hot_leads()
        stats = lm.get_pipeline_stats()
        progress = lm.get_days_to_goal()
        days_left = progress.get("days_remaining", 22)
        rev = progress.get("revenue", 0)
        remaining = progress.get("remaining", GOAL)

        actions = []
        if hot:
            top = hot[0]
            if lang == "EN":
                actions.append(
                    f"PRIORITY: Contact {top.email} (hot lead, {top.questions_asked} AI questions) "
                    f"via WhatsApp within 2h — highest conversion probability."
                )
            else:
                actions.append(
                    f"PRIORIDADE: Contatar {top.email} (lead quente, {top.questions_asked} perguntas à IA) "
                    f"via WhatsApp em até 2h — maior probabilidade de conversão."
                )

        if days_left <= 7:
            if lang == "EN":
                actions.append(
                    f"URGENCY: {days_left} days left. Need R${remaining:,.0f} more. "
                    f"Offer 30% discount for annual plan to accelerate closings."
                )
            else:
                actions.append(
                    f"URGÊNCIA: {days_left} dias restantes. Faltam R${remaining:,.0f}. "
                    f"Ofereça 30% de desconto no plano anual para acelerar fechamentos."
                )

        total = stats.get("total", 0)
        if total > 0:
            if lang == "EN":
                actions.append(
                    f"EMAIL BLAST: Run email sequences for all {total} leads now — "
                    f"Day 5 social proof email drives 18% conversion lift."
                )
            else:
                actions.append(
                    f"EMAIL MARKETING: Execute sequências de email para todos os {total} leads agora — "
                    f"email de prova social do Dia 5 gera 18% de aumento em conversão."
                )

        if not actions:
            if lang == "EN":
                actions = [
                    "Generate more demo leads by promoting the free AI trial on LinkedIn.",
                    "Review and update NCM monitoring for Chapter 30 high-value products.",
                    "Prepare enterprise proposal template for companies importing > R$10M/year.",
                ]
            else:
                actions = [
                    "Gere mais leads demo promovendo o trial grátis da IA no LinkedIn.",
                    "Revise e atualize o monitoramento de NCMs do Capítulo 30 de alto valor.",
                    "Prepare template de proposta enterprise para empresas que importam > R$10M/ano.",
                ]
        return actions[:3]
    except Exception as exc:
        return [f"Error generating suggestions: {exc}"]


# ---------------------------------------------------------------------------
# Tool definitions for Claude API
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "name": "get_pipeline",
        "description": "Get current sales pipeline statistics: lead counts by status, conversion rates, revenue.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_hot_leads",
        "description": "Get the leads most likely to convert (hot/warm, not yet subscribed).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "draft_whatsapp_message",
        "description": "Draft a personalized WhatsApp message for a specific lead.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Lead's email address"},
                "lang": {"type": "string", "description": "Language: PT or EN", "default": "PT"},
            },
            "required": ["email"],
        },
    },
    {
        "name": "draft_email_followup",
        "description": "Draft a personalized follow-up email for a specific lead.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Lead's email address"},
                "lang": {"type": "string", "description": "Language: PT or EN", "default": "PT"},
            },
            "required": ["email"],
        },
    },
    {
        "name": "get_daily_target",
        "description": "Get how many sales are needed per day to hit the R$50k goal by April 30.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_revenue_progress",
        "description": "Get current revenue vs target (R$50,000 goal).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "suggest_next_actions",
        "description": "Get AI suggestions for the 3 most impactful sales actions right now.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lang": {"type": "string", "description": "Language: PT or EN", "default": "PT"},
            },
            "required": [],
        },
    },
    {
        "name": "get_prospects",
        "description": "Get the outreach prospect list — companies to contact for sales (Brazil + international).",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status: pending, contacted, converted, all", "default": "pending"},
            },
            "required": [],
        },
    },
    {
        "name": "run_outreach",
        "description": "Trigger daily outreach — send personalized emails to up to 20 pending prospects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "daily_limit": {"type": "integer", "description": "Max emails to send (default 20)", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_outreach_stats",
        "description": "Get outreach pipeline stats: how many prospects are pending, contacted, converted, international.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

def _tool_get_prospects(status: str = "pending") -> list:
    """Get prospect list from outreach pipeline."""
    try:
        from src.db.database import get_prospects
        return get_prospects(status=status if status != "all" else None, limit=50)
    except Exception as exc:
        return [{"error": str(exc)}]


def _tool_run_outreach(daily_limit: int = 20) -> dict:
    """Trigger daily outreach emails to pending prospects."""
    try:
        from src.agents.outreach_agent import run_daily_outreach
        return run_daily_outreach(daily_limit=daily_limit)
    except Exception as exc:
        return {"error": str(exc)}


def _tool_get_outreach_stats() -> dict:
    """Get outreach pipeline stats — pending, contacted, converted."""
    try:
        from src.db.database import get_prospects
        all_p     = get_prospects(limit=500)
        pending   = [p for p in all_p if p["status"] == "pending" and p["email"]]
        contacted = [p for p in all_p if p["status"] == "contacted"]
        converted = [p for p in all_p if p["status"] == "converted"]
        no_email  = [p for p in all_p if not p["email"]]
        intl      = [p for p in all_p if not p.get("email", "").endswith(".com.br")]
        return {
            "total": len(all_p),
            "pending": len(pending),
            "contacted": len(contacted),
            "converted": len(converted),
            "no_email": len(no_email),
            "international": len(intl),
            "next_to_contact": [
                {"company": p["company_name"], "email": p["email"], "segment": p["segment"]}
                for p in pending[:5]
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


_TOOL_MAP = {
    "get_pipeline":           lambda inp: _tool_get_pipeline(),
    "get_hot_leads":          lambda inp: _tool_get_hot_leads(),
    "draft_whatsapp_message": lambda inp: _tool_draft_whatsapp(inp.get("email", ""), inp.get("lang", "PT")),
    "draft_email_followup":   lambda inp: _tool_draft_email(inp.get("email", ""), inp.get("lang", "PT")),
    "get_daily_target":       lambda inp: _tool_get_daily_target(),
    "get_revenue_progress":   lambda inp: _tool_get_revenue_progress(),
    "suggest_next_actions":   lambda inp: _tool_suggest_next_actions(inp.get("lang", "PT")),
    "get_prospects":          lambda inp: _tool_get_prospects(inp.get("status", "pending")),
    "run_outreach":           lambda inp: _tool_run_outreach(inp.get("daily_limit", 20)),
    "get_outreach_stats":     lambda inp: _tool_get_outreach_stats(),
}


# ---------------------------------------------------------------------------
# DirectorAgent
# ---------------------------------------------------------------------------

class DirectorAgent:
    """AI Sales Director — Anthropic primary, Groq fallback."""

    MODEL_ANTHROPIC = "claude-sonnet-4-6"
    MODEL_GROQ      = "llama-3.3-70b-versatile"

    def __init__(self):
        self._client      = None   # Anthropic
        self._groq_client = None   # Groq fallback
        self._history: list[dict] = []

        if ANTHROPIC_AVAILABLE:
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                self._client = _anthropic.Anthropic(api_key=api_key)

        # Always initialize Groq if key is available — used as primary (fast, reliable)
        if GROQ_AVAILABLE:
            groq_key = os.getenv("GROQ_API_KEY", "")
            if groq_key:
                self._groq_client = _Groq(api_key=groq_key)

    @property
    def is_online(self) -> bool:
        return self._client is not None or self._groq_client is not None

    def _get_system(self, lang: str) -> str:
        return _SYSTEM_EN if lang == "EN" else _SYSTEM_PT

    def _build_context_prompt(self, message: str, lang: str) -> str:
        """Inject live pipeline data into prompt for Groq (no tool calling)."""
        ctx = ""
        try:
            lm = _get_lead_manager()
            stats = lm.get_pipeline_stats()
            progress = lm.get_days_to_goal()
            hot = lm.get_hot_leads()
            hot_list = "\n".join(
                f"  - {l.email} ({l.country_hint or 'BR'}, {l.questions_asked} perguntas)"
                for l in hot[:5]
            ) or ("  (none)" if lang == "EN" else "  (nenhum)")
            ctx += (
                f"\n\n[DEMO PIPELINE DATA]\n"
                f"Total leads: {stats.get('total', 0)}\n"
                f"Hot leads: {len(hot)}\n"
                f"Revenue: R${progress.get('revenue', 0):,.0f} / R${GOAL:,.0f}\n"
                f"Remaining: R${progress.get('remaining', GOAL):,.0f} in {progress.get('days_remaining', 22)} days\n"
                f"Hot leads list:\n{hot_list}\n"
                f"Status breakdown: {json.dumps(stats.get('by_status', {}))}\n"
            )
        except Exception:
            pass
        try:
            outreach = _tool_get_outreach_stats()
            if "error" not in outreach:
                next_contacts = ", ".join(
                    f"{p['company']} ({p['email']})" for p in outreach.get("next_to_contact", [])
                ) or "none"
                ctx += (
                    f"\n[OUTREACH PIPELINE DATA]\n"
                    f"Total prospects: {outreach.get('total', 0)}\n"
                    f"Pending (email ready): {outreach.get('pending', 0)}\n"
                    f"Contacted: {outreach.get('contacted', 0)}\n"
                    f"Converted: {outreach.get('converted', 0)}\n"
                    f"International: {outreach.get('international', 0)}\n"
                    f"Next to contact: {next_contacts}\n"
                )
        except Exception:
            pass
        return message + ctx

    def _chat_groq(self, message: str, lang: str) -> str:
        """Chat via Groq with context injection instead of tool calling."""
        system = self._get_system(lang)
        enriched = self._build_context_prompt(message, lang)
        # Only include clean string history — skip any error msgs or complex objects
        messages = [{"role": "system", "content": system}]
        for m in self._history[-6:]:
            content = m.get("content", "")
            if isinstance(content, str) and content and not content.startswith("[Erro"):
                role = m.get("role", "")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": content[:800]})
        messages.append({"role": "user", "content": enriched})
        response = self._groq_client.chat.completions.create(
            model=self.MODEL_GROQ,
            messages=messages,
            max_tokens=1024,
            temperature=0.4,
        )
        return response.choices[0].message.content or ""

    def chat(self, message: str, lang: str = "PT") -> str:
        """Send a message and return the director's response.
        Priority: Groq (reliable, fast) → Anthropic (full tool calling) → fallback.
        """
        if not self._client and not self._groq_client:
            return self._fallback_response(message, lang)

        self._history.append({"role": "user", "content": message})

        # Try Groq first — context-enriched, always works
        if self._groq_client:
            try:
                text = self._chat_groq(message, lang)
                self._history.append({"role": "assistant", "content": text})
                return text
            except Exception as exc:
                logger.warning("Groq director failed, trying Anthropic: %s", exc)

        try:
            response = self._client.messages.create(
                model=self.MODEL_ANTHROPIC,
                max_tokens=2048,
                system=self._get_system(lang),
                tools=_TOOLS,
                messages=self._history,
            )

            # Agentic loop — handle tool calls
            while response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_fn = _TOOL_MAP.get(block.name)
                        if tool_fn:
                            try:
                                result = tool_fn(block.input)
                            except Exception as exc:
                                result = {"error": str(exc)}
                        else:
                            result = {"error": f"Unknown tool: {block.name}"}
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        })

                # Append assistant message with tool calls
                self._history.append({"role": "assistant", "content": response.content})
                # Append tool results
                self._history.append({"role": "user", "content": tool_results})

                response = self._client.messages.create(
                    model=self.MODEL_ANTHROPIC,
                    max_tokens=2048,
                    system=self._get_system(lang),
                    tools=_TOOLS,
                    messages=self._history,
                )

            # Extract text response
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text

            self._history.append({"role": "assistant", "content": text})
            return text

        except Exception as exc:
            logger.error("DirectorAgent.chat error: %s", exc)
            # Try Groq as emergency fallback before showing offline message
            if self._groq_client:
                try:
                    text = self._chat_groq(message, lang)
                    self._history.append({"role": "assistant", "content": text})
                    return text
                except Exception as exc2:
                    logger.error("Groq emergency fallback failed: %s", exc2)
            err_msg = f"[Erro API: {type(exc).__name__}: {str(exc)[:200]}]"
            return err_msg

    def get_daily_brief(self, lang: str = "PT") -> str:
        """Generate a daily briefing with pipeline status and priorities."""
        if lang == "EN":
            prompt = (
                "Generate my daily sales briefing. Use your tools to get the current pipeline, "
                "hot leads, revenue progress, and suggest the 3 most impactful actions for today. "
                "Format it as a clear, actionable executive summary."
            )
        else:
            prompt = (
                "Gere meu briefing diário de vendas. Use suas ferramentas para obter o pipeline atual, "
                "leads quentes, progresso de receita e sugerir as 3 ações mais impactantes para hoje. "
                "Formate como um resumo executivo claro e acionável."
            )
        # Brief uses a fresh context
        saved = self._history.copy()
        self._history = []
        result = self.chat(prompt, lang=lang)
        self._history = saved
        return result

    def reset(self) -> None:
        """Clear conversation history."""
        self._history = []

    def _fallback_response(self, message: str, lang: str) -> str:
        """Simple fallback when API is unavailable."""
        try:
            lm = _get_lead_manager()
            stats = lm.get_pipeline_stats()
            progress = lm.get_days_to_goal()
            hot = lm.get_hot_leads()

            total = stats.get("total", 0)
            revenue = progress.get("revenue", 0)
            remaining = progress.get("remaining", GOAL)
            days_left = progress.get("days_remaining", 22)
            hot_count = len(hot)

            if lang == "EN":
                return (
                    f"**Pipeline Summary** (offline mode — set ANTHROPIC_API_KEY for full AI)\n\n"
                    f"- Total leads: {total}\n"
                    f"- Hot leads: {hot_count}\n"
                    f"- Revenue: R${revenue:,.0f} / R${GOAL:,.0f}\n"
                    f"- Remaining: R${remaining:,.0f} in {days_left} days\n\n"
                    f"Top priority: contact hot leads immediately via WhatsApp."
                )
            else:
                return (
                    f"**Resumo do Pipeline** (modo offline — configure ANTHROPIC_API_KEY para IA completa)\n\n"
                    f"- Leads totais: {total}\n"
                    f"- Leads quentes: {hot_count}\n"
                    f"- Receita: R${revenue:,.0f} / R${GOAL:,.0f}\n"
                    f"- Faltam: R${remaining:,.0f} em {days_left} dias\n\n"
                    f"Prioridade: contatar leads quentes imediatamente via WhatsApp."
                )
        except Exception:
            if lang == "EN":
                return "Director AI offline. Set ANTHROPIC_API_KEY to enable full capabilities."
            return "Diretora IA offline. Configure ANTHROPIC_API_KEY para habilitar todas as funcionalidades."
