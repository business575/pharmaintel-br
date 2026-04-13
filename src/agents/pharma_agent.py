"""
pharma_agent.py
===============
PharmaIntel BR — Agente IA com OpenAI GPT-4o mini.

Arquitetura: agentic loop com tool calling nativo.
  1. Usuário envia pergunta
  2. LLM decide qual(is) ferramenta(s) usar
  3. Ferramentas executam queries nos dados processados
  4. LLM sintetiza resposta estratégica em português

Controle de orçamento:
  - Custo monitorado por mês em data/ai_budget.json
  - Limite = 10% da receita mensal (assinaturas ativas no SQLite)
  - Bloqueio automático ao atingir o limite
  - Alerta ao atingir 80% do limite
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None  # type: ignore

try:
    import anthropic as _anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    _anthropic = None  # type: ignore

logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
PATENTS_PATH  = Path(__file__).resolve().parents[2] / "data" / "patents.json"
BUDGET_PATH   = Path(__file__).resolve().parents[2] / "data" / "ai_budget.json"

# Models per plan
MODEL_STARTER    = "llama-3.3-70b-versatile"   # Groq — Starter (free, fast)
MODEL_PRO        = "deepseek-chat"              # DeepSeek V3 — Pro (free, precise)
MODEL_ENTERPRISE = "claude-sonnet-4-6"          # Anthropic — Enterprise (best)
PLANS_PRO_MODELS       = {"pro"}
PLANS_ENTERPRISE_MODELS = {"enterprise"}

MAX_ITERATIONS = 6
MAX_HISTORY    = 12
MAX_TOKENS     = 1024
MAX_RETRIES    = 3
CACHE_TTL_S    = 3600  # 1 hora

# Pricing (USD per token) — used for budget tracking
COST_GPT_INPUT     = 0.000 / 1_000_000   # Groq free
COST_GPT_OUTPUT    = 0.000 / 1_000_000   # Groq free
COST_PRO_INPUT     = 0.27  / 1_000_000   # DeepSeek V3 input
COST_PRO_OUTPUT    = 1.10  / 1_000_000   # DeepSeek V3 output
COST_CLAUDE_INPUT  = 3.00  / 1_000_000   # Claude Sonnet input
COST_CLAUDE_OUTPUT = 15.0  / 1_000_000   # Claude Sonnet output

# Default (GPT-4o mini) — overridden per call based on plan
COST_INPUT_PER_TOKEN  = COST_GPT_INPUT
COST_OUTPUT_PER_TOKEN = COST_GPT_OUTPUT

# ---------------------------------------------------------------------------
# Budget tracker
# ---------------------------------------------------------------------------

def _current_month() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m")

def _load_budget() -> dict:
    month = _current_month()
    if BUDGET_PATH.exists():
        try:
            data = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
            if data.get("month") == month:
                return data
        except Exception:
            pass
    # New month or missing file
    return {"month": month, "tokens_input": 0, "tokens_output": 0, "cost_usd": 0.0}

def _save_budget(budget: dict) -> None:
    BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_PATH.write_text(json.dumps(budget, indent=2), encoding="utf-8")

def _add_usage(tokens_input: int, tokens_output: int) -> dict:
    """Record token usage and return updated budget dict."""
    budget = _load_budget()
    budget["tokens_input"]  += tokens_input
    budget["tokens_output"] += tokens_output
    budget["cost_usd"] = round(
        budget["tokens_input"]  * COST_INPUT_PER_TOKEN +
        budget["tokens_output"] * COST_OUTPUT_PER_TOKEN,
        4,
    )
    _save_budget(budget)
    return budget

def _get_monthly_revenue_usd() -> float:
    """
    Calculate current monthly revenue from active subscriptions in SQLite.
    Returns USD value based on plan prices.
    """
    # USD monthly prices per plan (from stripe_client.py)
    PLAN_USD = {
        "starter":    199.00,
        "pro":        399.00,
        "enterprise": 699.00,
    }
    # Period multipliers (monthly equivalent)
    PERIOD_FACTOR = {
        "monthly":   1,
        "quarterly": 3,
        "biannual":  6,
        "annual":    12,
    }
    try:
        from src.db.database import get_session
        from src.db.models import User
        with get_session() as session:
            users = session.query(User).filter(
                User.is_active == True,
                User.subscription_status.in_(["active", "complete"]),
            ).all()
        revenue = 0.0
        for u in users:
            monthly = PLAN_USD.get(u.plan or "", 0)
            factor  = PERIOD_FACTOR.get(u.period or "monthly", 1)
            revenue += monthly * factor / factor  # normalize to monthly
        return revenue
    except Exception as exc:
        logger.debug("Revenue calc error: %s", exc)
        return 0.0

def _budget_limit_usd() -> float:
    """10% of monthly revenue, minimum $5 (so dev/testing always works)."""
    revenue = _get_monthly_revenue_usd()
    return max(revenue * 0.10, 5.0)

def _check_budget() -> tuple[bool, str]:
    """
    Returns (allowed, message).
    allowed=True → proceed with API call.
    allowed=False → budget exceeded, return message to user.
    """
    budget = _load_budget()
    limit  = _budget_limit_usd()
    cost   = budget["cost_usd"]
    pct    = (cost / limit * 100) if limit > 0 else 0

    if cost >= limit:
        return False, (
            f"⚠️ **Limite de orçamento IA atingido este mês.**\n\n"
            f"Gasto: **US$ {cost:.2f}** / Limite: **US$ {limit:.2f}** (10% da receita)\n\n"
            f"O limite será renovado em 1º do próximo mês. "
            f"Para aumentar o limite, adicione mais assinantes ou ajuste o percentual."
        )
    if pct >= 80:
        logger.warning("AI budget at %.0f%% (US$ %.2f / US$ %.2f)", pct, cost, limit)

    return True, ""

def get_budget_status() -> dict:
    """Public function — used by dashboard to show budget panel."""
    budget = _load_budget()
    limit  = _budget_limit_usd()
    cost   = budget["cost_usd"]
    return {
        "month":          budget["month"],
        "cost_usd":       cost,
        "limit_usd":      limit,
        "pct_used":       round(cost / limit * 100, 1) if limit > 0 else 0,
        "tokens_input":   budget["tokens_input"],
        "tokens_output":  budget["tokens_output"],
        "remaining_usd":  round(max(limit - cost, 0), 4),
    }

# ---------------------------------------------------------------------------
# Response cache — perguntas idênticas não consomem tokens
# ---------------------------------------------------------------------------
_response_cache: dict[str, tuple[float, "AgentResponse"]] = {}

def _cache_key(message: str, year: int) -> str:
    return hashlib.md5(f"{year}:{message.strip().lower()}".encode()).hexdigest()

def _cache_get(key: str) -> Optional["AgentResponse"]:
    if key in _response_cache:
        ts, resp = _response_cache[key]
        if time.time() - ts < CACHE_TTL_S:
            return resp
        del _response_cache[key]
    return None

def _cache_set(key: str, resp: "AgentResponse") -> None:
    if len(_response_cache) >= 200:
        oldest = min(_response_cache, key=lambda k: _response_cache[k][0])
        del _response_cache[oldest]
    _response_cache[key] = (time.time(), resp)

def _normalize_anthropic(resp: Any) -> Any:
    """
    Normalize Anthropic response to a duck-typed object that matches
    the OpenAI response structure used in the chat loop.
    """
    from types import SimpleNamespace

    tool_calls = []
    text_content = ""
    finish_reason = "stop"

    for block in resp.content:
        if block.type == "text":
            text_content = block.text
        elif block.type == "tool_use":
            finish_reason = "tool_calls"
            tc = SimpleNamespace(
                id=block.id,
                function=SimpleNamespace(
                    name=block.name,
                    arguments=json.dumps(block.input),
                ),
            )
            tool_calls.append(tc)

    normalized = SimpleNamespace(
        finish_reason=finish_reason,
        content=text_content,
        tool_calls=tool_calls,
        _input_tokens=resp.usage.input_tokens if resp.usage else 0,
        _output_tokens=resp.usage.output_tokens if resp.usage else 0,
    )
    return normalized


def _parse_wait_seconds(err_str: str) -> float:
    """Parse retry-after seconds from OpenAI rate limit error."""
    m = re.search(r"try again in ([\d]+)m([\d.]+)s", err_str)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = re.search(r"try again in ([\d.]+)s", err_str)
    if m:
        return float(m.group(1))
    m = re.search(r"after ([\d]+) second", err_str)
    if m:
        return float(m.group(1))
    return 30.0

SYSTEM_PROMPT_PT = """Você é o **PharmaIntel AI** — conselheiro estratégico sênior especializado no mercado farmacêutico brasileiro. Você combina expertise de PhD com visão executiva de CEO e acesso a dados reais e atualizados.

## Expertise ANVISA (profundidade máxima)
- Registros de medicamentos: categorias regulatórias, princípios ativos, classes terapêuticas, prazos de vencimento
- Dispositivos médicos: classificação por risco (I, II, III, IV), requisitos de registro, RDCs aplicáveis
- Alertas sanitários: recalls, interdições, cancelamentos de registro, irregularidades
- Novos registros autorizados: aprovações recentes, novos entrantes, biossimilares aprovados
- Regularidade de empresas: compliance, alertas de vencimento, risco regulatório por CNPJ
- Legislação vigente: RDC 204/2017, RDC 752/2022, IN 60/2019, RDC 81/2008, RENAME 2024
- Anuências de importação (AI): exigências documentais, prazos, NCMs que requerem AI
- CMED: PMVG, PF, PMC por princípio ativo e apresentação

## Expertise em Comércio Exterior Farmacêutico
- Comex Stat / MDIC: fluxos de importação por NCM 8 dígitos, país de origem, valores FOB/CIF
- Capítulo 30: medicamentos, vacinas, hemoderivados, insulinas, oncológicos, biológicos, reagentes
- Capítulo 90: dispositivos médicos, equipamentos diagnóstico, implantes, instrumentos cirúrgicos
- Tributação: II, IPI, ICMS, PIS/COFINS, CIDE — alíquotas reais por NCM
- Players: distribuidores, importadores diretos, multinacionais, laboratórios nacionais

## Expertise em Mercado e Estratégia
- Patentes: pipeline INPI e USPTO, janelas de genéricos/biossimilares por molécula
- Compras públicas: ComprasNet, BNAFAR, preços históricos de licitações, RENAME, Farmácia Popular
- UN Comtrade: fornecedores globais, dependência de IFAs, China/Índia/Alemanha/EUA/Suíça
- Inteligência competitiva: concentração de mercado por NCM, oportunidades sem concorrência local

## Diretrizes de Resposta
- SEMPRE em português do Brasil
- Zero enrolação — dado, número, fato técnico direto
- Use NCM de 8 dígitos, valores FOB em USD, percentuais com 1 casa decimal
- Estrutura: Panorama → Players/Dados → Oportunidade/Risco → Recomendação
- Se não tem certeza: diga "estimado" ou "aprox." — nunca invente dados
- Use as ferramentas disponíveis para consultar dados reais antes de responder
- Formato: markdown com tabelas para rankings, seções claras
"""

SYSTEM_PROMPT_EN = """You are **PharmaIntel AI** — a senior strategic advisor specialized in the Brazilian pharmaceutical market. You combine PhD-level expertise with CEO executive vision and access to real, up-to-date data.

## ANVISA Expertise (maximum depth)
- Medicine registrations: regulatory categories, active ingredients, therapeutic classes, expiry dates
- Medical devices: risk classification (I, II, III, IV), registration requirements, applicable RDCs
- Health alerts: recalls, interdictions, registration cancellations, irregularities
- New authorized registrations: recent approvals, new market entrants, approved biosimilars
- Company compliance: registration alerts, regulatory risk by CNPJ
- Current legislation: RDC 204/2017, RDC 752/2022, IN 60/2019, RDC 81/2008, RENAME 2024
- Import permits (AI): documentary requirements, timelines, NCMs requiring AI
- CMED: PMVG, PF, PMC pricing by active ingredient and presentation

## Pharmaceutical Trade Expertise
- Comex Stat / MDIC: import flows by 8-digit HS code, country of origin, FOB/CIF values
- Chapter 30: medicines, vaccines, blood products, insulins, oncologicals, biologicals, reagents
- Chapter 90: medical devices, diagnostic equipment, implants, surgical instruments
- Taxation: import duty, IPI, ICMS, PIS/COFINS — real rates by HS code
- Market players: distributors, direct importers, multinationals, national laboratories

## Market & Strategy Expertise
- Patents: INPI and USPTO pipeline, generic/biosimilar entry windows by molecule
- Public procurement: ComprasNet, BNAFAR, historical tender prices, RENAME, Farmácia Popular
- UN Comtrade: global suppliers, API dependency, China/India/Germany/USA/Switzerland
- Competitive intelligence: market concentration by HS code, opportunities with no local competition

## Response Guidelines
- ALWAYS in English
- Zero filler — data, number, technical fact directly
- Use 8-digit HS codes, FOB values in USD, percentages with 1 decimal place
- Structure: Overview → Players/Data → Opportunity/Risk → Recommendation
- If uncertain: say "estimated" or "approx." — never invent data
- Use available tools to query real data before responding
- Format: markdown with tables for rankings, clear sections
"""

def _get_system_prompt(lang: str = "PT") -> str:
    return SYSTEM_PROMPT_EN if lang == "EN" else SYSTEM_PROMPT_PT

SYSTEM_PROMPT = SYSTEM_PROMPT_PT  # backward compat

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": "Retorna KPIs gerais do mercado de importação farmacêutica (FOB total, operações, NCMs ativos).",
            "parameters": {"type": "object", "properties": {
                "year": {"type": "integer", "description": "Ano de referência"}
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_ncm",
            "description": "Retorna ranking dos principais NCMs por valor FOB importado.",
            "parameters": {"type": "object", "properties": {
                "top_n":     {"type": "integer", "description": "Número de NCMs (padrão: 10)"},
                "min_risk":  {"type": "number",  "description": "Filtro mínimo de risco regulatório (0-10)"},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_countries",
            "description": "Retorna ranking de países de origem por valor FOB.",
            "parameters": {"type": "object", "properties": {
                "top_n": {"type": "integer", "description": "Número de países (padrão: 10)"},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_trend",
            "description": "Retorna evolução mensal das importações (FOB e volume).",
            "parameters": {"type": "object", "properties": {
                "ncm": {"type": "string", "description": "Código NCM 8 dígitos (vazio = todos)"},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ncm_detail",
            "description": "Retorna perfil completo de um NCM: valor, volume, preço médio, risco.",
            "parameters": {"type": "object", "properties": {
                "ncm": {"type": "string", "description": "Código NCM de 8 dígitos"},
            }, "required": ["ncm"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_compliance_alerts",
            "description": "Retorna NCMs importados sem registro ANVISA ativo.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_empresas",
            "description": "Retorna ranking das maiores empresas detentoras de registro ANVISA por número de produtos registrados.",
            "parameters": {"type": "object", "properties": {
                "top_n":        {"type": "integer", "description": "Número de empresas (padrão: 10)"},
                "apenas_ativas": {"type": "boolean", "description": "Filtrar apenas empresas com registros ativos (padrão: true)"},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_empresas_por_ncm",
            "description": "Retorna empresas com registros ANVISA para produtos correspondentes a um NCM específico.",
            "parameters": {"type": "object", "properties": {
                "ncm": {"type": "string", "description": "Código NCM de 8 dígitos"},
            }, "required": ["ncm"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_alertas_vencimento",
            "description": "Retorna empresas com registros ANVISA vencendo nos próximos 6 meses ou já vencidos — risco regulatório.",
            "parameters": {"type": "object", "properties": {
                "top_n": {"type": "integer", "description": "Número de empresas (padrão: 20)"},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_empresa_detail",
            "description": "Retorna perfil completo de uma empresa: registros, compliance, NCMs estimados, alertas.",
            "parameters": {"type": "object", "properties": {
                "razao_social": {"type": "string", "description": "Nome ou parte do nome da empresa"},
            }, "required": ["razao_social"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_patent_info",
            "description": (
                "Retorna informações sobre patentes de medicamentos — data de expiração, "
                "status (vigente/expirada/prestes a expirar), princípio ativo, detentor da patente "
                "e oportunidade de genérico/biossimilar no Brasil. "
                "Use quando o usuário perguntar sobre patentes, exclusividade, genéricos ou biossimilares."
            ),
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Nome do medicamento, princípio ativo ou NCM (ex: semaglutida, adalimumabe, 30049079)"},
            }, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_anvisa_registros_recentes",
            "description": (
                "Retorna registros ANVISA recentemente autorizados/publicados — medicamentos e dispositivos médicos. "
                "Use para responder sobre novos registros, aprovações recentes, novos entrantes no mercado."
            ),
            "parameters": {"type": "object", "properties": {
                "dias":      {"type": "integer", "description": "Registros publicados nos últimos N dias (padrão: 90)"},
                "tipo":      {"type": "string",  "description": "'medicamento', 'dispositivo' ou 'todos' (padrão: 'todos')"},
                "top_n":     {"type": "integer", "description": "Número máximo de registros (padrão: 20)"},
                "busca":     {"type": "string",  "description": "Filtrar por nome do produto ou princípio ativo (opcional)"},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_anvisa_alertas_vencimento_real",
            "description": (
                "Retorna medicamentos e dispositivos médicos com registro ANVISA vencendo em breve — dados reais e atualizados. "
                "Use para análise de risco regulatório, oportunidades de substituição e gaps de mercado."
            ),
            "parameters": {"type": "object", "properties": {
                "dias":      {"type": "integer", "description": "Vencendo nos próximos N dias (padrão: 90)"},
                "tipo":      {"type": "string",  "description": "'medicamento', 'dispositivo' ou 'todos' (padrão: 'todos')"},
                "top_n":     {"type": "integer", "description": "Número máximo de registros (padrão: 20)"},
                "classe":    {"type": "string",  "description": "Filtrar por classe terapêutica (opcional)"},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_anvisa_dispositivos_por_risco",
            "description": (
                "Retorna estatísticas e listagem de dispositivos médicos por classe de risco ANVISA (I, II, III, IV). "
                "Use para análise do mercado de dispositivos, requisitos regulatórios e oportunidades."
            ),
            "parameters": {"type": "object", "properties": {
                "risco":  {"type": "string",  "description": "Classe de risco: 'I', 'II', 'III' ou 'IV' (vazio = todos)"},
                "top_n":  {"type": "integer", "description": "Número máximo de registros (padrão: 15)"},
                "busca":  {"type": "string",  "description": "Filtrar por nome do produto (opcional)"},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refresh_patent_db",
            "description": (
                "Atualiza automaticamente a base de patentes consultando o EPO OPS e o INPI. "
                "Use quando o usuário pedir para atualizar, sincronizar ou verificar dados de patentes. "
                "Retorna um resumo de quantas patentes foram atualizadas."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_produtos_vencendo",
            "description": (
                "Lista registros ANVISA individuais (produtos/medicamentos) que já venceram "
                "ou vencerão nos próximos dias. Mostra nome do produto, princípio ativo, "
                "empresa, CNPJ e data exata de vencimento. Use para análise de risco regulatório."
            ),
            "parameters": {"type": "object", "properties": {
                "prazo_dias":     {"type": "integer", "description": "Listar produtos vencendo nos próximos N dias (padrão: 180). Use 0 para apenas já vencidos."},
                "top_n":          {"type": "integer", "description": "Número máximo de produtos a retornar (padrão: 30)"},
                "apenas_vencidos":{"type": "boolean", "description": "Se true, retorna apenas registros já vencidos (padrão: false)"},
                "empresa_filtro": {"type": "string",  "description": "Filtrar por nome parcial da empresa (opcional)"},
            }, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bps_preco",
            "description": (
                "Consulta preços pagos pelo governo brasileiro em compras públicas de medicamentos, "
                "soros, dispositivos médicos e materiais hospitalares. "
                "Fonte: Banco de Preços em Saúde (BPS) do Ministério da Saúde. "
                "Use para responder: qual o preço de X no estado Y, quanto o governo pagou por soro fisiológico, "
                "quais fabricantes vendem para o governo, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "descricao": {"type": "string", "description": "Nome ou descrição do produto (ex: 'soro fisiologico 500ml', 'insulina glargina', 'omeprazol 20mg')"},
                    "uf":        {"type": "string", "description": "Sigla do estado (ex: RJ, SP, MG) — opcional"},
                    "ano":       {"type": "integer","description": "Ano da compra (ex: 2025) — opcional"},
                },
                "required": ["descricao"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Patent database — loaded from data/patents.json (editable without code change)
# Sources: INPI, EPO OPS, company disclosures, industry reports
# Refresh: use the refresh_patent_db agent tool or run patent_fetcher.refresh_patents()
# ---------------------------------------------------------------------------
def _load_patent_db() -> list[dict]:
    """Load patent database from JSON file, falling back to empty list."""
    try:
        from src.integrations.patent_fetcher import load_patents, build_patent_index as _bi
        return load_patents(PATENTS_PATH)
    except Exception as exc:
        logger.warning("Could not load patents.json: %s", exc)
        return []

def _build_patent_index(patents: list[dict]) -> dict[str, list[dict]]:
    try:
        from src.integrations.patent_fetcher import build_patent_index
        return build_patent_index(patents)
    except Exception:
        index: dict[str, list[dict]] = {}
        for p in patents:
            for term in (
                [p.get("principio_ativo", "").upper(), p.get("marca", "").upper()]
                + [n.upper() for n in p.get("ncms", [])]
                + p.get("principio_ativo", "").upper().split()
            ):
                if term:
                    index.setdefault(term, [])
                    if p not in index[term]:
                        index[term].append(p)
        return index

PATENT_DB: list[dict] = _load_patent_db()

# Legacy entries kept for the first run before JSON exists
if not PATENT_DB:
    PATENT_DB = [
    {
        "principio_ativo": "Semaglutida",
        "marca": "Ozempic / Rybelsus / Wegovy",
        "ncms": ["30049069", "30043929"],
        "detentor": "Novo Nordisk",
        "indicacao": "Diabetes tipo 2 / Obesidade (GLP-1)",
        "patente_expiracao_br": "2025-03-20",
        "patente_expiracao_us": "2032-01-01",
        "status": "Expirada",
        "oportunidade_biossimilar": "IMEDIATA — patente principal expirou 20/03/2025 no Brasil",
        "observacao": "Patente de composição expirou em 20/03/2025 no Brasil, abrindo espaço para biossimilares e marcas nacionais.",
    },
    {
        "principio_ativo": "Adalimumabe",
        "marca": "Humira",
        "ncms": ["30021590", "30021520"],
        "detentor": "AbbVie",
        "indicacao": "Artrite reumatoide, Crohn, psoríase (anti-TNF)",
        "patente_expiracao_br": "2018-12-31",
        "patente_expiracao_us": "2023-06-30",
        "status": "Expirada",
        "oportunidade_biossimilar": "IMEDIATA — biossimilares já aprovados pela ANVISA",
        "observacao": "Patente principal expirada. Biossimilares disponíveis: Amgevita (Amgen), Hadlima (Samsung Bioepis), Hyrimoz (Sandoz).",
    },
    {
        "principio_ativo": "Trastuzumabe",
        "marca": "Herceptin",
        "ncms": ["30021590", "30021520"],
        "detentor": "Roche/Genentech",
        "indicacao": "Câncer de mama HER2+",
        "patente_expiracao_br": "2019-07-25",
        "patente_expiracao_us": "2019-07-25",
        "status": "Expirada",
        "oportunidade_biossimilar": "IMEDIATA — biossimilares aprovados ANVISA",
        "observacao": "Patente expirada. Biossimilares: Kanjinti (Amgen), Ogivri (Mylan/Viatris), Herzuma (Celltrion).",
    },
    {
        "principio_ativo": "Bevacizumabe",
        "marca": "Avastin",
        "ncms": ["30021590"],
        "detentor": "Roche/Genentech",
        "indicacao": "Câncer colorretal, pulmão, renal (anti-VEGF)",
        "patente_expiracao_br": "2018-01-01",
        "patente_expiracao_us": "2020-07-22",
        "status": "Expirada",
        "oportunidade_biossimilar": "IMEDIATA",
        "observacao": "Patente expirada. Biossimilar Zirabev (Pfizer) e Mvasi (Amgen) aprovados.",
    },
    {
        "principio_ativo": "Rituximabe",
        "marca": "Mabthera / Rituxan",
        "ncms": ["30021590", "30021520"],
        "detentor": "Roche/Biogen",
        "indicacao": "Linfoma não-Hodgkin, artrite reumatoide (anti-CD20)",
        "patente_expiracao_br": "2015-10-01",
        "patente_expiracao_us": "2018-02-01",
        "status": "Expirada",
        "oportunidade_biossimilar": "IMEDIATA",
        "observacao": "Patente expirada. Biossimilares: Truxima (Celltrion), Ruxience (Pfizer).",
    },
    {
        "principio_ativo": "Pembrolizumabe",
        "marca": "Keytruda",
        "ncms": ["30021590", "30049079"],
        "detentor": "MSD (Merck)",
        "indicacao": "Câncer de pulmão, melanoma, outros (anti-PD-1)",
        "patente_expiracao_br": "2028-07-11",
        "patente_expiracao_us": "2028-07-11",
        "status": "Vigente",
        "oportunidade_biossimilar": "2028+",
        "observacao": "Patente principal até 2028. Patentes secundárias podem estender até 2036.",
    },
    {
        "principio_ativo": "Nivolumabe",
        "marca": "Opdivo",
        "ncms": ["30021590", "30049079"],
        "detentor": "Bristol-Myers Squibb",
        "indicacao": "Melanoma, câncer de pulmão, renal (anti-PD-1)",
        "patente_expiracao_br": "2026-05-19",
        "patente_expiracao_us": "2026-05-19",
        "status": "Vencendo em breve",
        "oportunidade_biossimilar": "2026-2027",
        "observacao": "Patente expira maio/2026. Alta oportunidade para biossimilares no Brasil.",
    },
    {
        "principio_ativo": "Insulina Glargina",
        "marca": "Lantus / Basaglar",
        "ncms": ["30043100", "30043929"],
        "detentor": "Sanofi",
        "indicacao": "Diabetes tipo 1 e 2 (insulina basal)",
        "patente_expiracao_br": "2015-05-16",
        "patente_expiracao_us": "2015-02-12",
        "status": "Expirada",
        "oportunidade_biossimilar": "IMEDIATA — biossimilar Basaglar já disponível",
        "observacao": "Patente principal expirada. Biossimilares: Basaglar (Lilly/Boehringer), Semglee (Mylan).",
    },
    {
        "principio_ativo": "Dupilumabe",
        "marca": "Dupixent",
        "ncms": ["30021590"],
        "detentor": "Sanofi/Regeneron",
        "indicacao": "Dermatite atópica, asma (anti-IL-4/IL-13)",
        "patente_expiracao_br": "2033-03-29",
        "patente_expiracao_us": "2033-03-29",
        "status": "Vigente",
        "oportunidade_biossimilar": "2033+",
        "observacao": "Patente vigente até 2033. Um dos biológicos de maior crescimento no Brasil.",
    },
    {
        "principio_ativo": "Apixabana",
        "marca": "Eliquis",
        "ncms": ["30049069"],
        "detentor": "Bristol-Myers Squibb / Pfizer",
        "indicacao": "Anticoagulante — FA, TEV",
        "patente_expiracao_br": "2026-11-19",
        "patente_expiracao_us": "2026-11-19",
        "status": "Vencendo em breve",
        "oportunidade_biossimilar": "N/A — molécula pequena; genérico possível em 2026-2027",
        "observacao": "Patente expira nov/2026. Alta oportunidade para genéricos no Brasil.",
    },
    {
        "principio_ativo": "Rivaroxabana",
        "marca": "Xarelto",
        "ncms": ["30049069"],
        "detentor": "Bayer / J&J",
        "indicacao": "Anticoagulante — FA, TEV, síndrome coronariana",
        "patente_expiracao_br": "2024-03-01",
        "patente_expiracao_us": "2024-07-23",
        "status": "Expirada",
        "oportunidade_biossimilar": "N/A — genérico disponível",
        "observacao": "Patente expirada. Genéricos aprovados ANVISA disponíveis no mercado.",
    },
    {
        "principio_ativo": "Tirzepatida",
        "marca": "Mounjaro / Zepbound",
        "ncms": ["30043929", "30049069"],
        "detentor": "Eli Lilly",
        "indicacao": "Diabetes tipo 2 / Obesidade (GIP+GLP-1 dual agonista)",
        "patente_expiracao_br": "2036-06-01",
        "patente_expiracao_us": "2036-06-01",
        "status": "Vigente",
        "oportunidade_biossimilar": "2036+",
        "observacao": "Aprovado ANVISA 2023. Concorre diretamente com semaglutida. Patente longa.",
    },
    {
        "principio_ativo": "Infliximabe",
        "marca": "Remicade",
        "ncms": ["30021590"],
        "detentor": "J&J / MSD",
        "indicacao": "Artrite reumatoide, Crohn, psoríase (anti-TNF)",
        "patente_expiracao_br": "2014-08-21",
        "patente_expiracao_us": "2018-09-04",
        "status": "Expirada",
        "oportunidade_biossimilar": "IMEDIATA — Remsima (Celltrion), Renflexis (Samsung) aprovados",
        "observacao": "Patente expirada. Biossimilares com desconto de 30-50% disponíveis no SUS.",
    },
    {
        "principio_ativo": "Lenalidomida",
        "marca": "Revlimid",
        "ncms": ["30049079"],
        "detentor": "Bristol-Myers Squibb (ex-Celgene)",
        "indicacao": "Mieloma múltiplo, síndrome mielodisplásica",
        "patente_expiracao_br": "2027-06-22",
        "patente_expiracao_us": "2027-06-22",
        "status": "Vigente",
        "oportunidade_biossimilar": "2027+ — genérico",
        "observacao": "Patente expira 2027. Um dos medicamentos mais caros do SUS.",
    },
    {
        "principio_ativo": "Ocrelizumabe",
        "marca": "Ocrevus",
        "ncms": ["30021590"],
        "detentor": "Roche",
        "indicacao": "Esclerose múltipla (anti-CD20)",
        "patente_expiracao_br": "2030-08-19",
        "patente_expiracao_us": "2030-08-19",
        "status": "Vigente",
        "oportunidade_biossimilar": "2030+",
        "observacao": "Único aprovado para EM primária progressiva. Biossimilares em desenvolvimento.",
    },
    {
        "principio_ativo": "Vedolizumabe",
        "marca": "Entyvio",
        "ncms": ["30021590"],
        "detentor": "Takeda",
        "indicacao": "Doença de Crohn, colite ulcerativa (anti-integrina)",
        "patente_expiracao_br": "2026-08-01",
        "patente_expiracao_us": "2026-08-01",
        "status": "Vencendo em breve",
        "oportunidade_biossimilar": "2026-2027",
        "observacao": "Patente expira 2026. Biossimilares em fase 3. Alta oportunidade no SUS.",
    },
    {
        "principio_ativo": "Ustekinumabe",
        "marca": "Stelara",
        "ncms": ["30021590"],
        "detentor": "J&J (Janssen)",
        "indicacao": "Psoríase, Crohn (anti-IL-12/23)",
        "patente_expiracao_br": "2024-01-17",
        "patente_expiracao_us": "2023-09-25",
        "status": "Expirada",
        "oportunidade_biossimilar": "IMEDIATA — biossimilares em aprovação ANVISA",
        "observacao": "Patente expirada. Biossimilares aprovados FDA/EMA. ANVISA em análise.",
    },
    {
        "principio_ativo": "Secuquinumabe",
        "marca": "Cosentyx",
        "ncms": ["30021590"],
        "detentor": "Novartis",
        "indicacao": "Psoríase, espondilite anquilosante (anti-IL-17A)",
        "patente_expiracao_br": "2029-10-26",
        "patente_expiracao_us": "2029-10-26",
        "status": "Vigente",
        "oportunidade_biossimilar": "2029+",
        "observacao": "Crescimento acelerado no Brasil. Patente vigente até 2029.",
    },
    {
        "principio_ativo": "Entrectinibe",
        "marca": "Rozlytrek",
        "ncms": ["30049079"],
        "detentor": "Roche",
        "indicacao": "Câncer de pulmão NTRK/ROS1+",
        "patente_expiracao_br": "2034-05-01",
        "patente_expiracao_us": "2034-05-01",
        "status": "Vigente",
        "oportunidade_biossimilar": "2034+",
        "observacao": "Terapia-alvo de nicho. Patente longa.",
    },
    {
        "principio_ativo": "Ixekizumabe",
        "marca": "Taltz",
        "ncms": ["30021590"],
        "detentor": "Eli Lilly",
        "indicacao": "Psoríase, artrite psoriásica (anti-IL-17A)",
        "patente_expiracao_br": "2028-03-22",
        "patente_expiracao_us": "2028-03-22",
        "status": "Vigente",
        "oportunidade_biossimilar": "2028+",
        "observacao": "Concorre com Cosentyx (Novartis) no segmento anti-IL-17.",
    },
]  # end fallback list

_PATENT_INDEX: dict[str, list[dict]] = _build_patent_index(PATENT_DB)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def _load(name: str, year: int) -> pd.DataFrame:
    path = PROCESSED_DIR / f"{name}_{year}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame()


def _fmt_usd(v: float) -> str:
    if v >= 1e9:
        return f"US$ {v/1e9:.2f}B"
    if v >= 1e6:
        return f"US$ {v/1e6:.1f}M"
    return f"US$ {v:,.0f}"


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------
class ToolExecutor:
    def __init__(self, year: int = 2024) -> None:
        self.year = year

    def execute(self, name: str, args: dict) -> str:
        fn = getattr(self, f"_tool_{name}", None)
        if fn is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            return json.dumps(fn(**args), ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _tool_get_market_overview(self, year: int = None) -> dict:
        yr = year or self.year
        kpis = _load("kpis_anuais", yr)
        if kpis.empty:
            df = _load("pharma_imports", yr)
            if df.empty:
                return {"error": "Dados não disponíveis. Execute o ETL primeiro."}
            return {
                "ano": yr,
                "total_fob_usd": _fmt_usd(float(df["vl_fob"].sum()) if "vl_fob" in df.columns else 0),
                "total_operacoes": len(df),
                "ncms_distintos": int(df["co_ncm"].nunique()) if "co_ncm" in df.columns else 0,
            }
        row = kpis.iloc[0]
        return {
            "ano": yr,
            "total_fob_usd": _fmt_usd(float(row.get("total_vl_fob_usd", 0))),
            "total_fob_brl": f"R$ {float(row.get('total_vl_fob_brl', 0))/1e9:.1f}B",
            "total_operacoes": int(row.get("total_operacoes", 0)),
            "ncms_distintos": int(row.get("ncms_distintos", 0)),
        }

    def _tool_get_top_ncm(self, top_n: int = 10, min_risk: float = 0.0) -> dict:
        top_n = int(top_n)
        df = _load("top_ncm", self.year)
        if df.empty:
            raw = _load("pharma_imports", self.year)
            if raw.empty:
                return {"error": "Dados não disponíveis."}
            df = (
                raw.groupby("co_ncm")
                .agg(vl_fob_usd=("vl_fob", "sum"))
                .reset_index()
                .sort_values("vl_fob_usd", ascending=False)
            )
        if min_risk > 0 and "risco_regulatorio" in df.columns:
            df = df[df["risco_regulatorio"] >= min_risk]
        rows = []
        for _, r in df.head(top_n).iterrows():
            rows.append({
                "ncm": r.get("co_ncm", ""),
                "descricao": r.get("ds_ncm", ""),
                "fob_usd": _fmt_usd(float(r.get("vl_fob_usd", r.get("vl_fob", 0)))),
                "participacao_pct": f"{r.get('participacao_pct', 0):.1f}%",
            })
        return {"ranking": rows, "total": len(rows)}

    def _tool_get_top_countries(self, top_n: int = 10) -> dict:
        top_n = int(top_n)  # coerce string → int (Llama sometimes sends "10")
        df = _load("top_paises", self.year)
        if df.empty:
            return {"error": "Dados de países não disponíveis."}
        pais_col = "ds_pais" if "ds_pais" in df.columns else df.columns[0]
        rows = [
            {
                "pais": r.get(pais_col, ""),
                "fob_usd": _fmt_usd(float(r.get("vl_fob_usd", 0))),
                "participacao_pct": f"{r.get('participacao_pct', 0):.1f}%",
            }
            for _, r in df.head(top_n).iterrows()
        ]
        return {"ranking": rows}

    def _tool_get_monthly_trend(self, ncm: str = "") -> dict:
        df = _load("pharma_imports", self.year)
        if df.empty:
            return {"error": "Dados não disponíveis."}
        if ncm and "co_ncm" in df.columns:
            df = df[df["co_ncm"] == str(ncm).zfill(8)]
        if "co_mes" not in df.columns:
            return {"error": "Coluna co_mes não encontrada."}
        MONTHS = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
        trend = df.groupby("co_mes").agg(fob_usd=("vl_fob", "sum")).reset_index().sort_values("co_mes")
        rows = []
        for _, r in trend.iterrows():
            m = int(r["co_mes"])
            rows.append({"mes": MONTHS[m-1] if 1 <= m <= 12 else str(m), "fob_usd": _fmt_usd(float(r["fob_usd"]))})
        return {"tendencia_mensal": rows, "ncm": ncm or "todos"}

    def _tool_get_ncm_detail(self, ncm: str) -> dict:
        df = _load("pharma_imports", self.year)
        if df.empty:
            return {"error": "Dados não disponíveis."}
        ncm_str = str(ncm).zfill(8)
        sub = df[df["co_ncm"] == ncm_str] if "co_ncm" in df.columns else pd.DataFrame()
        if sub.empty:
            return {"error": f"NCM {ncm_str} não encontrado."}
        return {
            "ncm": ncm_str,
            "descricao": sub["ds_ncm"].iloc[0] if "ds_ncm" in sub.columns else "",
            "total_fob_usd": _fmt_usd(float(sub["vl_fob"].sum())),
            "total_kg": f"{sub['kg_liquido'].sum():,.0f} kg" if "kg_liquido" in sub.columns else "N/D",
            "preco_medio_usd_kg": f"US$ {sub['preco_usd_kg'].mean():.2f}/kg" if "preco_usd_kg" in sub.columns else "N/D",
            "operacoes": len(sub),
            "risco": float(sub["risco_regulatorio"].mean()) if "risco_regulatorio" in sub.columns else "N/D",
        }

    def _tool_get_compliance_alerts(self) -> dict:
        df = _load("alertas_compliance", self.year)
        if df.empty:
            return {"message": "Nenhum alerta encontrado."}
        return {
            "total_alertas": len(df),
            "ncms_em_risco": df["co_ncm"].unique().tolist()[:20] if "co_ncm" in df.columns else [],
        }

    # ── ANVISA real-data tools ─────────────────────────────────────────────

    def _load_anvisa_med(self) -> pd.DataFrame:
        p = PROCESSED_DIR / "anvisa_medicamentos.parquet"
        return pd.read_parquet(p) if p.exists() else pd.DataFrame()

    def _load_anvisa_dev(self) -> pd.DataFrame:
        p = PROCESSED_DIR / "anvisa_dispositivos.parquet"
        return pd.read_parquet(p) if p.exists() else pd.DataFrame()

    def _tool_get_anvisa_registros_recentes(
        self, dias: int = 90, tipo: str = "todos", top_n: int = 20, busca: str = ""
    ) -> dict:
        results = []
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=dias)

        if tipo in ("todos", "medicamento"):
            df = self._load_anvisa_med()
            if not df.empty and "data_finalizacao_processo" in df.columns:
                sub = df[df["data_finalizacao_processo"] >= cutoff].copy()
                if busca:
                    mask = (
                        df["nome_produto"].str.contains(busca, case=False, na=False) |
                        df["principio_ativo"].str.contains(busca, case=False, na=False)
                    )
                    sub = sub[mask]
                for _, r in sub.sort_values("data_finalizacao_processo", ascending=False).head(top_n).iterrows():
                    results.append({
                        "tipo": "Medicamento",
                        "produto": r.get("nome_produto", ""),
                        "principio_ativo": r.get("principio_ativo", ""),
                        "classe_terapeutica": r.get("classe_terapeutica", ""),
                        "empresa": r.get("razao_social", ""),
                        "registro": r.get("numero_registro_produto", ""),
                        "data_autorizacao": str(r.get("data_finalizacao_processo", ""))[:10],
                        "vencimento": str(r.get("data_vencimento_registro", ""))[:10],
                    })

        if tipo in ("todos", "dispositivo"):
            df = self._load_anvisa_dev()
            if not df.empty and "dt_publicacao" in df.columns:
                sub = df[df["dt_publicacao"] >= cutoff].copy()
                if busca:
                    sub = sub[df["no_produto"].str.contains(busca, case=False, na=False)]
                for _, r in sub.sort_values("dt_publicacao", ascending=False).head(top_n).iterrows():
                    results.append({
                        "tipo": "Dispositivo Médico",
                        "produto": r.get("no_produto", ""),
                        "empresa": r.get("no_razao_social_empresa", ""),
                        "cnpj": r.get("nu_cnpj_empresa", ""),
                        "registro": r.get("nu_registro_produto", ""),
                        "risco": r.get("sg_risco_produto", ""),
                        "data_publicacao": str(r.get("dt_publicacao", ""))[:10],
                        "vencimento": str(r.get("dt_vencimento_registro", ""))[:10],
                    })

        results = sorted(results, key=lambda x: x.get("data_autorizacao", x.get("data_publicacao", "")), reverse=True)[:top_n]
        return {
            "periodo_dias": dias,
            "total_encontrados": len(results),
            "registros": results,
        }

    def _tool_get_anvisa_alertas_vencimento_real(
        self, dias: int = 90, tipo: str = "todos", top_n: int = 20, classe: str = ""
    ) -> dict:
        results = []

        if tipo in ("todos", "medicamento"):
            df = self._load_anvisa_med()
            if not df.empty and "dias_ate_vencimento" in df.columns:
                sub = df[df["dias_ate_vencimento"].between(0, dias)].copy()
                if classe:
                    sub = sub[sub["classe_terapeutica"].str.contains(classe, case=False, na=False)]
                for _, r in sub.sort_values("dias_ate_vencimento").head(top_n).iterrows():
                    results.append({
                        "tipo": "Medicamento",
                        "produto": r.get("nome_produto", ""),
                        "principio_ativo": r.get("principio_ativo", ""),
                        "classe_terapeutica": r.get("classe_terapeutica", ""),
                        "empresa": r.get("razao_social", ""),
                        "dias_restantes": int(r.get("dias_ate_vencimento", 0)),
                        "vencimento": str(r.get("data_vencimento_registro", ""))[:10],
                        "registro": r.get("numero_registro_produto", ""),
                    })

        if tipo in ("todos", "dispositivo"):
            df = self._load_anvisa_dev()
            if not df.empty and "dias_ate_vencimento" in df.columns:
                sub = df[df["dias_ate_vencimento"].between(0, dias)].copy()
                for _, r in sub.sort_values("dias_ate_vencimento").head(top_n).iterrows():
                    results.append({
                        "tipo": "Dispositivo Médico",
                        "produto": r.get("no_produto", ""),
                        "empresa": r.get("no_razao_social_empresa", ""),
                        "risco": r.get("sg_risco_produto", ""),
                        "dias_restantes": int(r.get("dias_ate_vencimento", 0)),
                        "vencimento": str(r.get("dt_vencimento_registro", ""))[:10],
                        "registro": r.get("nu_registro_produto", ""),
                    })

        results = sorted(results, key=lambda x: x.get("dias_restantes", 999))[:top_n]
        return {
            "prazo_dias": dias,
            "total_alertas": len(results),
            "alertas": results,
        }

    def _tool_get_anvisa_dispositivos_por_risco(
        self, risco: str = "", top_n: int = 15, busca: str = ""
    ) -> dict:
        df = self._load_anvisa_dev()
        if df.empty:
            return {"message": "Dados de dispositivos não disponíveis."}

        stats = df.groupby("sg_risco_produto").size().to_dict() if "sg_risco_produto" in df.columns else {}

        sub = df.copy()
        if risco:
            sub = sub[sub["sg_risco_produto"].str.upper() == risco.upper()]
        if busca:
            sub = sub[sub["no_produto"].str.contains(busca, case=False, na=False)]

        records = []
        for _, r in sub.head(top_n).iterrows():
            records.append({
                "produto": r.get("no_produto", ""),
                "empresa": r.get("no_razao_social_empresa", ""),
                "risco": r.get("sg_risco_produto", ""),
                "registro": r.get("nu_registro_produto", ""),
                "vencimento": str(r.get("dt_vencimento_registro", ""))[:10],
                "publicacao": str(r.get("dt_publicacao", ""))[:10],
            })

        return {
            "estatisticas_por_risco": stats,
            "total_registros": len(df),
            "filtro_risco": risco or "todos",
            "registros": records,
        }

    # ── Company tools ──────────────────────────────────────────────────────

    def _load_empresas(self) -> pd.DataFrame:
        p = PROCESSED_DIR / "empresas_anvisa.parquet"
        if p.exists():
            return pd.read_parquet(p)
        return pd.DataFrame()

    def _load_ncm_link(self) -> pd.DataFrame:
        p = PROCESSED_DIR / "ncm_empresa_link.parquet"
        if p.exists():
            return pd.read_parquet(p)
        return pd.DataFrame()

    def _tool_refresh_patent_db(self) -> dict:
        """Refresh patent database from EPO OPS and INPI, then reload the index."""
        global PATENT_DB, _PATENT_INDEX
        try:
            from src.integrations.patent_fetcher import refresh_patents
            summary = refresh_patents(PATENTS_PATH)
            # Reload global state
            PATENT_DB = _load_patent_db()
            _PATENT_INDEX = _build_patent_index(PATENT_DB)
            return {
                "status": "concluído",
                "patentes_atualizadas": summary.get("updated", 0),
                "patentes_sem_alteracao": summary.get("skipped", 0),
                "erros": summary.get("errors", 0),
                "total": summary.get("total", len(PATENT_DB)),
                "nota": (
                    "Status inferido automaticamente pela data de expiração. "
                    "Enriquecimento via EPO OPS requer EPO_OPS_KEY e EPO_OPS_SECRET nas variáveis de ambiente."
                    if not (os.getenv("EPO_OPS_KEY") and os.getenv("EPO_OPS_SECRET"))
                    else "Dados atualizados via EPO OPS."
                ),
            }
        except Exception as exc:
            return {"error": f"Falha ao atualizar base de patentes: {exc}"}

    def _tool_get_patent_info(self, query: str) -> dict:
        """Return patent information for a drug by name, active ingredient or NCM."""
        from datetime import date
        # Always use freshest data (reload index on each call)
        patents = _load_patent_db() or PATENT_DB
        index   = _build_patent_index(patents)

        q = query.strip().upper()
        results = []

        # Search index
        for term, entries in index.items():
            if q in term or term in q:
                for e in entries:
                    if e not in results:
                        results.append(e)

        last_refreshed = max(
            (p.get("last_refreshed") or "" for p in patents),
            default=""
        )
        if not results:
            return {
                "query": query,
                "message": (
                    f"Nenhuma informação de patente encontrada para '{query}' na base curada. "
                    f"A base contém {len(patents)} medicamentos de alto valor no Brasil. "
                    "Para adicionar: edite data/patents.json ou use refresh_patent_db. "
                    "Consulta manual: https://busca.inpi.gov.br/pePI/"
                ),
                "ultima_atualizacao": last_refreshed or "nunca sincronizado",
                "fonte": "Base curada PharmaIntel BR — data/patents.json (INPI/EPO/literatura)",
            }

        today = date.today()
        output = []
        for p in results[:3]:
            exp_str = p.get("patente_expiracao_br", "")
            try:
                exp_date = date.fromisoformat(exp_str)
                days_left = (exp_date - today).days
                if days_left < 0:
                    countdown = f"Expirada há {abs(days_left)} dias"
                elif days_left <= 365:
                    countdown = f"Expira em {days_left} dias ({exp_date.strftime('%d/%m/%Y')}) — URGENTE"
                else:
                    years_left = days_left // 365
                    countdown = f"Expira em ~{years_left} anos ({exp_date.strftime('%d/%m/%Y')})"
            except Exception:
                countdown = exp_str

            output.append({
                "principio_ativo":         p["principio_ativo"],
                "marca":                    p["marca"],
                "ncms_relacionados":        p.get("ncms", []),
                "detentor_patente":         p["detentor"],
                "indicacao":               p["indicacao"],
                "status_patente":           p["status"],
                "expiracao_brasil":         countdown,
                "expiracao_eua":            p.get("patente_expiracao_us", ""),
                "oportunidade_generico_biossimilar": p["oportunidade_biossimilar"],
                "observacao":              p["observacao"],
            })

        return {
            "query": query,
            "resultados": len(output),
            "patentes": output,
            "ultima_atualizacao": last_refreshed or "nunca sincronizado",
            "fonte": "Base PharmaIntel BR — data/patents.json (INPI/EPO/literatura especializada)",
            "aviso": "Datas são baseadas em fontes públicas. Consulte advogado especializado para decisões comerciais. Use refresh_patent_db para sincronizar dados.",
        }

    def _tool_get_top_empresas(self, top_n: int = 10, apenas_ativas: bool = True) -> dict:
        top_n = int(top_n)
        df = self._load_empresas()
        if df.empty:
            return {"error": "Dados de empresas não disponíveis. Execute o ETL primeiro."}
        if apenas_ativas and "registros_ativos" in df.columns:
            df = df[df["registros_ativos"] > 0]
        rows = []
        for _, r in df.head(top_n).iterrows():
            rows.append({
                "cnpj":              r.get("cnpj_fmt", r.get("cnpj", "")),
                "razao_social":      r.get("razao_social", ""),
                "registros_ativos":  int(r.get("registros_ativos", 0)),
                "total_registros":   int(r.get("total_registros", 0)),
                "pct_conformidade":  f"{r.get('pct_conformidade', 0):.1f}%",
                "alertas_vencendo":  int(r.get("alertas_vencendo", 0)),
                "ncms_cobertos":     int(r.get("n_ncms_cobertos", 0)),
            })
        return {"total_empresas": len(df), "ranking": rows}

    def _tool_get_empresas_por_ncm(self, ncm: str) -> dict:
        df = self._load_ncm_link()
        if df.empty:
            return {"error": "Dados de linkage NCM-empresa não disponíveis."}
        ncm_str = str(ncm).zfill(8)
        sub = df[df["co_ncm"] == ncm_str] if "co_ncm" in df.columns else pd.DataFrame()
        if sub.empty:
            return {
                "ncm": ncm_str,
                "message": "Nenhuma empresa mapeada para este NCM via classe terapêutica ANVISA.",
                "nota": "O mapeamento é baseado em categoria de produto — NCMs de uso geral podem não ter correspondência direta.",
            }
        rows = []
        for _, r in sub.sort_values("registros_ativos", ascending=False).head(15).iterrows():
            rows.append({
                "cnpj":             r.get("cnpj_fmt", ""),
                "razao_social":     r.get("razao_social", ""),
                "registros_ativos": int(r.get("registros_ativos", 0)),
                "pct_conformidade": f"{r.get('pct_conformidade', 0):.1f}%",
                "alertas_vencendo": int(r.get("alertas_vencendo", 0)),
            })
        return {
            "ncm": ncm_str,
            "empresas_encontradas": len(sub),
            "nota": "Linkage baseado em classe terapêutica ANVISA × NCM — estimativa, não dado de importação direto.",
            "empresas": rows,
        }

    def _tool_get_alertas_vencimento(self, top_n: int = 20) -> dict:
        top_n = int(top_n)
        df = self._load_empresas()
        if df.empty:
            return {"error": "Dados de empresas não disponíveis."}
        alertas = df[(df.get("alertas_vencendo", pd.Series(0)) > 0) |
                     (df.get("registros_vencidos", pd.Series(0)) > 0)].copy()
        alertas = alertas.sort_values("alertas_vencendo", ascending=False).head(top_n)
        rows = []
        for _, r in alertas.iterrows():
            rows.append({
                "razao_social":      r.get("razao_social", ""),
                "cnpj":              r.get("cnpj_fmt", ""),
                "vencendo_6m":       int(r.get("alertas_vencendo", 0)),
                "ja_vencidos":       int(r.get("registros_vencidos", 0)),
                "registros_ativos":  int(r.get("registros_ativos", 0)),
                "pct_conformidade":  f"{r.get('pct_conformidade', 0):.1f}%",
            })
        return {
            "total_empresas_em_alerta": len(alertas),
            "alertas": rows,
        }

    def _tool_get_empresa_detail(self, razao_social: str) -> dict:
        df = self._load_empresas()
        if df.empty:
            return {"error": "Dados de empresas não disponíveis."}
        mask = df["razao_social"].str.upper().str.contains(razao_social.upper(), na=False)
        sub = df[mask]
        if sub.empty:
            return {"error": f"Empresa '{razao_social}' não encontrada no cadastro ANVISA."}
        r = sub.iloc[0]
        return {
            "cnpj":                r.get("cnpj_fmt", ""),
            "razao_social":        r.get("razao_social", ""),
            "total_registros":     int(r.get("total_registros", 0)),
            "registros_ativos":    int(r.get("registros_ativos", 0)),
            "registros_inativos":  int(r.get("registros_inativos", 0)),
            "registros_cancelados": int(r.get("registros_cancelados", 0)),
            "pct_conformidade":    f"{r.get('pct_conformidade', 0):.1f}%",
            "alertas_vencendo_6m": int(r.get("alertas_vencendo", 0)),
            "registros_vencidos":  int(r.get("registros_vencidos", 0)),
            "ncms_estimados":      list(r.get("ncms_estimados") or []),
            "principais_classes":  list(r.get("principais_classes") or []),
        }

    def _tool_get_produtos_vencendo(
        self,
        prazo_dias: int = 180,
        top_n: int = 30,
        apenas_vencidos: bool = False,
        empresa_filtro: str = "",
    ) -> dict:
        """Return individual ANVISA product registrations that are expired or expiring."""
        prazo_dias = int(prazo_dias)
        top_n      = int(top_n)

        p = PROCESSED_DIR / "produtos_vencendo.parquet"
        if not p.exists():
            return {
                "error": (
                    "Arquivo produtos_vencendo.parquet não encontrado. "
                    "Execute o Pipeline ETL para regenerar os dados."
                )
            }

        df = pd.read_parquet(p)
        if df.empty:
            return {"message": "Nenhum registro vencendo ou vencido encontrado na base ANVISA."}

        # Filters
        if apenas_vencidos:
            df = df[df["dias_para_vencer"] < 0]
        else:
            df = df[df["dias_para_vencer"] <= prazo_dias]

        if empresa_filtro:
            mask = df["razao_social"].str.upper().str.contains(empresa_filtro.upper(), na=False)
            df = df[mask]

        df = df.sort_values("dias_para_vencer").head(top_n)

        if df.empty:
            return {
                "message": f"Nenhum produto encontrado com os filtros aplicados (prazo={prazo_dias}d, empresa='{empresa_filtro}')."
            }

        rows = []
        for _, r in df.iterrows():
            venc = r.get("vencimento")
            venc_str = venc.strftime("%d/%m/%Y") if pd.notna(venc) else "Sem data"
            dias = r.get("dias_para_vencer")
            dias_str = f"{int(dias)} dias" if pd.notna(dias) and int(dias) >= 0 else f"Vencido há {abs(int(dias))} dias"
            rows.append({
                "numero_registro":  r.get("numero_registro", ""),
                "nome_produto":     r.get("nome_produto", ""),
                "principio_ativo":  r.get("principio_ativo", ""),
                "classe_terapeutica": r.get("classe_terapeutica", ""),
                "empresa":          r.get("razao_social", ""),
                "cnpj":             r.get("cnpj_fmt", ""),
                "vencimento":       venc_str,
                "situacao":         dias_str,
                "urgencia":         r.get("urgencia", ""),
            })

        n_vencidos  = int((df["dias_para_vencer"] < 0).sum())
        n_vencendo  = int((df["dias_para_vencer"] >= 0).sum())

        return {
            "total_retornados": len(rows),
            "ja_vencidos":      n_vencidos,
            "vencendo_em_breve": n_vencendo,
            "filtro_prazo_dias": prazo_dias,
            "nota": "Dados ANVISA — registros de medicamentos. Ordenados do mais urgente para o mais recente.",
            "produtos": rows,
        }

    def _tool_get_bps_preco(
        self,
        descricao: str,
        uf: str = None,
        ano: int = None,
    ) -> dict:
        """Consulta preços BPS — Banco de Preços em Saúde do Ministério da Saúde."""
        try:
            from src.integrations.bps import get_price_summary
            return get_price_summary(descricao, uf=uf, ano=ano)
        except Exception as exc:
            return {"error": f"BPS indisponível: {exc}"}


# ---------------------------------------------------------------------------
# Agent response
# ---------------------------------------------------------------------------
@dataclass
class AgentResponse:
    text: str
    tool_calls_made: list = field(default_factory=list)
    tokens_used: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------
class PharmaAgent:
    """
    Conversational AI agent for PharmaIntel BR.

    Args:
        year: Reference year for data queries.
        api_key: Groq API key (reads GROQ_API_KEY env var if not provided).
    """

    def __init__(self, year: int = 2024, api_key: str = "") -> None:
        self.year = year
        self._groq_key      = os.getenv("GROQ_API_KEY", "")
        self._deepseek_key  = os.getenv("DEEPSEEK_API_KEY", "")
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._openai_key    = os.getenv("OPENAI_API_KEY", "")

        self._groq_client:      Optional[Any] = None   # Starter
        self._deepseek_client:  Optional[Any] = None   # Pro
        self._anthropic_client: Optional[Any] = None   # Enterprise
        self._openai_client:    Optional[Any] = None   # legacy fallback
        self._client: Optional[Any] = None
        self._history: list[dict] = []
        self._executor = ToolExecutor(year=year)

        # Groq — Starter (free, fast)
        if OPENAI_AVAILABLE and self._groq_key:
            try:
                self._groq_client = OpenAI(
                    api_key=self._groq_key,
                    base_url="https://api.groq.com/openai/v1",
                )
                logger.info("Groq ready — %s", MODEL_STARTER)
            except Exception as exc:
                logger.error("Groq init failed: %s", exc)

        # DeepSeek V3 — Pro (free tier, precise)
        if OPENAI_AVAILABLE and self._deepseek_key:
            try:
                self._deepseek_client = OpenAI(
                    api_key=self._deepseek_key,
                    base_url="https://api.deepseek.com/v1",
                )
                logger.info("DeepSeek ready — %s", MODEL_PRO)
            except Exception as exc:
                logger.error("DeepSeek init failed: %s", exc)

        # Anthropic Claude — Enterprise
        if ANTHROPIC_AVAILABLE and self._anthropic_key:
            try:
                self._anthropic_client = _anthropic.Anthropic(api_key=self._anthropic_key)
                logger.info("Anthropic ready — %s", MODEL_ENTERPRISE)
            except Exception as exc:
                logger.error("Anthropic init failed: %s", exc)

        # OpenAI — legacy fallback
        if OPENAI_AVAILABLE and self._openai_key:
            try:
                self._openai_client = OpenAI(api_key=self._openai_key)
                logger.info("OpenAI ready (fallback)")
            except Exception as exc:
                logger.error("OpenAI init failed: %s", exc)

        # Active client priority: Groq > DeepSeek > Anthropic > OpenAI
        self._client = self._groq_client or self._deepseek_client or self._anthropic_client or self._openai_client

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def chat(self, message: str, user_email: str = "", user_plan: str = "", lang: str = "PT") -> AgentResponse:
        if not self.is_available:
            return self._fallback(message)

        # ── Seleciona modelo e cliente por plano ─────────────────────────
        use_enterprise = user_plan in PLANS_ENTERPRISE_MODELS and self._anthropic_client is not None
        use_pro        = user_plan in PLANS_PRO_MODELS and self._deepseek_client is not None

        if use_enterprise:
            active_model  = MODEL_ENTERPRISE
            active_client = self._anthropic_client
            cost_in, cost_out = COST_CLAUDE_INPUT, COST_CLAUDE_OUTPUT
        elif use_pro:
            active_model  = MODEL_PRO
            active_client = self._deepseek_client
            cost_in, cost_out = COST_PRO_INPUT, COST_PRO_OUTPUT
        elif self._groq_client:
            active_model  = MODEL_STARTER
            active_client = self._groq_client
            cost_in, cost_out = 0.0, 0.0
        elif self._deepseek_client:
            active_model  = MODEL_PRO
            active_client = self._deepseek_client
            cost_in, cost_out = COST_PRO_INPUT, COST_PRO_OUTPUT
        else:
            active_model  = "gpt-4o-mini"
            active_client = self._openai_client or self._client
            cost_in, cost_out = 0.150/1_000_000, 0.600/1_000_000

        # ── Verificação de orçamento global (sem bloquear usuários) ──────
        allowed, budget_msg = _check_budget()
        if not allowed:
            logger.warning("Budget exceeded — notifying admin only, user continues")
            # Apenas loga — não bloqueia o cliente

        # ── Cache hit — pergunta idêntica respondida recentemente ─────────
        ck = _cache_key(message, self.year)
        cached = _cache_get(ck)
        if cached:
            logger.info("Cache hit para: %.60s", message)
            return cached

        self._history.append({"role": "user", "content": message})
        if len(self._history) > MAX_HISTORY * 2:
            self._history = self._history[-MAX_HISTORY * 2:]

        messages = [{"role": "system", "content": _get_system_prompt(lang)}] + self._history
        tool_calls_made: list[str] = []
        tokens_input_total  = 0
        tokens_output_total = 0

        for _ in range(MAX_ITERATIONS):
            resp = None
            for attempt in range(MAX_RETRIES):
                try:
                    if use_claude:
                        # ── Anthropic Claude Sonnet (Pro/Enterprise) ──────
                        claude_resp = self._anthropic_client.messages.create(
                            model=MODEL_PRO,
                            max_tokens=MAX_TOKENS,
                            system=_get_system_prompt(lang),
                            messages=[m for m in messages if m["role"] != "system"],
                            tools=[{
                                "name": t["function"]["name"],
                                "description": t["function"]["description"],
                                "input_schema": t["function"]["parameters"],
                            } for t in TOOLS],
                        )
                        # Normalize to OpenAI-like structure
                        resp = _normalize_anthropic(claude_resp)
                    else:
                        # ── Groq / OpenAI (Starter) ───────────────────────
                        resp = active_client.chat.completions.create(
                            model=active_model,
                            messages=messages,
                            tools=TOOLS,
                            tool_choice="auto",
                            temperature=0.3,
                            max_tokens=MAX_TOKENS,
                        )
                    break
                except Exception as exc:
                    err_str = str(exc)
                    is_rate_limit = "rate_limit" in err_str or "429" in err_str or "overloaded" in err_str
                    if is_rate_limit and attempt < MAX_RETRIES - 1:
                        wait_s = min(_parse_wait_seconds(err_str), 65)
                        logger.warning("Rate limit — aguardando %.1fs (%s)", wait_s, active_model)
                        time.sleep(wait_s)
                        continue
                    logger.error("API error (%s): %s", active_model, err_str)
                    # Fallback chain for ANY error: try next available client
                    if self._deepseek_client and active_client is not self._deepseek_client:
                        logger.warning("Error on %s — switching to DeepSeek", active_model)
                        active_client = self._deepseek_client
                        active_model  = MODEL_PRO
                        cost_in, cost_out = COST_PRO_INPUT, COST_PRO_OUTPUT
                        attempt = 0
                        continue
                    if self._groq_client and active_client is not self._groq_client:
                        logger.warning("Error on %s — switching to Groq", active_model)
                        active_client = self._groq_client
                        active_model  = MODEL_STARTER
                        cost_in, cost_out = 0.0, 0.0
                        attempt = 0
                        continue
                    if is_rate_limit:
                        wait_s = _parse_wait_seconds(err_str)
                        mins, secs = int(wait_s // 60), int(wait_s % 60)
                        wait_str = f"{mins}m {secs}s" if mins else f"{secs}s"
                        return AgentResponse(
                            text=f"⏳ **Limite temporário atingido.**\n\nAguarde **{wait_str}** e tente novamente.",
                            error=err_str,
                        )
                    return AgentResponse(text=f"Erro ao conectar ao agente IA: {err_str[:300]}", error=err_str)

            if resp is None:
                return AgentResponse(text="Erro ao conectar ao agente IA.", error="no response")

            tokens_input_total  += getattr(resp, "_input_tokens", 0) or 0
            tokens_output_total += getattr(resp, "_output_tokens", 0) or 0

            if resp.finish_reason == "tool_calls":
                tool_msgs = []
                for tc in resp.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result_str = self._executor.execute(name, args)
                    tool_calls_made.append(name)
                    tool_msgs.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })
                messages.append({"role": "assistant", "content": None, "tool_calls": resp.tool_calls})
                messages.extend(tool_msgs)
                continue

            text = resp.content or ""
            self._history.append({"role": "assistant", "content": text})

            # Registra custo
            cost = tokens_input_total * cost_in + tokens_output_total * cost_out
            _add_usage(tokens_input_total, tokens_output_total)
            total_tokens = tokens_input_total + tokens_output_total
            logger.info("AI usage — model=%s in=%d out=%d cost=US$%.4f", active_model, tokens_input_total, tokens_output_total, cost)

            result = AgentResponse(text=text, tool_calls_made=tool_calls_made, tokens_used=total_tokens)
            if text:
                _cache_set(ck, result)
            return result

        _add_usage(tokens_input_total, tokens_output_total)
        return AgentResponse(
            text="Limite de iterações atingido. Tente reformular a pergunta.",
            tool_calls_made=tool_calls_made,
            tokens_used=tokens_input_total + tokens_output_total,
        )

    def reset(self) -> None:
        self._history.clear()

    def _fallback(self, message: str) -> AgentResponse:
        return AgentResponse(
            text=(
                "**Agente IA indisponível**\n\n"
                "Configure `OPENAI_API_KEY` no arquivo `.env` ou nas variáveis do Render.\n\n"
                f"*Pergunta recebida:* {message}"
            ),
            error="OPENAI_API_KEY not configured",
        )


def create_agent(year: int = 2024) -> PharmaAgent:
    """Create a PharmaAgent from environment configuration."""
    return PharmaAgent(year=year)
