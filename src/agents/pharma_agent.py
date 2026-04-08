"""
pharma_agent.py
===============
PharmaIntel BR — Agente IA com Groq + Llama 3.3 70B.

Arquitetura: agentic loop com tool calling nativo.
  1. Usuário envia pergunta
  2. LLM decide qual(is) ferramenta(s) usar
  3. Ferramentas executam queries nos dados processados
  4. LLM sintetiza resposta estratégica em português
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    Groq = None  # type: ignore

logger = logging.getLogger(__name__)

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
PATENTS_PATH  = Path(__file__).resolve().parents[2] / "data" / "patents.json"
GROQ_MODEL    = "llama-3.3-70b-versatile"
MAX_ITERATIONS = 6
MAX_HISTORY    = 12          # reduzido de 20 → economiza tokens por requisição
MAX_TOKENS     = 1024        # reduzido de 2048 → ~50% menos tokens por resposta
MAX_RETRIES    = 3           # tentativas em caso de rate limit
CACHE_TTL_S    = 3600        # cache de respostas: 1 hora

# ---------------------------------------------------------------------------
# Response cache — evita chamar Groq para perguntas idênticas
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
    # Limita o cache a 200 entradas para não vazar memória
    if len(_response_cache) >= 200:
        oldest = min(_response_cache, key=lambda k: _response_cache[k][0])
        del _response_cache[oldest]
    _response_cache[key] = (time.time(), resp)

def _parse_wait_seconds(err_str: str) -> float:
    """Parse seconds to wait from Groq rate limit error message."""
    m = re.search(r"try again in ([\d]+)m([\d.]+)s", err_str)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = re.search(r"try again in ([\d.]+)s", err_str)
    if m:
        return float(m.group(1))
    return 60.0  # default: wait 60s

SYSTEM_PROMPT = """Você é o **PharmaIntel AI** — especialista em mercado farmacêutico brasileiro com profundo conhecimento em:

• Regulatório ANVISA (registros, RDCs, INs, vigilância sanitária)
• Comércio exterior farmacêutico (Capítulos 30 e 90 da TEC/NCM)
• Inteligência competitiva e estratégia de importação
• Compras públicas (PNAFAR, RENAME, BNAFAR, ComprasNet)
• Precificação CMED/PMVG e câmbio

## Diretrizes
- Responda SEMPRE em português do Brasil
- Seja direto, quantitativo e baseado em dados reais
- Cite NCMs, valores FOB em USD e BRL, participações percentuais
- Identifique riscos regulatórios e oportunidades de mercado

## Formato
Use markdown com tabelas em rankings. Estruture respostas longas com seções.
"""

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
        self._api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self._client: Optional[Any] = None
        self._history: list[dict] = []
        self._executor = ToolExecutor(year=year)

        if GROQ_AVAILABLE and self._api_key:
            try:
                self._client = Groq(api_key=self._api_key)
                logger.info("Groq ready — model: %s", GROQ_MODEL)
            except Exception as exc:
                logger.error("Groq init failed: %s", exc)
        else:
            reason = "groq not installed" if not GROQ_AVAILABLE else "GROQ_API_KEY not set"
            logger.warning("Agent in fallback mode: %s", reason)

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def chat(self, message: str) -> AgentResponse:
        if not self.is_available:
            return self._fallback(message)

        # ── Cache hit — pergunta idêntica respondida recentemente ─────────
        ck = _cache_key(message, self.year)
        cached = _cache_get(ck)
        if cached:
            logger.info("Cache hit para: %.60s", message)
            return cached

        self._history.append({"role": "user", "content": message})
        # Mantém apenas as últimas MAX_HISTORY trocas → economiza tokens
        if len(self._history) > MAX_HISTORY * 2:
            self._history = self._history[-MAX_HISTORY * 2:]

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self._history
        tool_calls_made: list[str] = []
        tokens_used = 0

        for _ in range(MAX_ITERATIONS):
            # ── Retry com backoff em caso de rate limit ───────────────────
            resp = None
            for attempt in range(MAX_RETRIES):
                try:
                    resp = self._client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=messages,
                        tools=TOOLS,
                        tool_choice="auto",
                        temperature=0.3,
                        max_tokens=MAX_TOKENS,
                    )
                    break  # sucesso — sai do retry loop
                except Exception as exc:
                    err_str = str(exc)
                    is_rate_limit = "rate_limit" in err_str or "429" in err_str

                    if is_rate_limit and attempt < MAX_RETRIES - 1:
                        wait_s = _parse_wait_seconds(err_str)
                        wait_s = min(wait_s, 65)  # nunca espera mais de 65s
                        logger.warning(
                            "Groq rate limit — aguardando %.1fs (tentativa %d/%d)",
                            wait_s, attempt + 1, MAX_RETRIES,
                        )
                        time.sleep(wait_s)
                        continue

                    # Rate limit esgotado após retries, ou outro erro
                    logger.error("Groq API error: %s", err_str)
                    if is_rate_limit:
                        wait_s = _parse_wait_seconds(err_str)
                        mins = int(wait_s // 60)
                        secs = int(wait_s % 60)
                        wait_str = f"{mins}m {secs}s" if mins else f"{secs}s"
                        result = AgentResponse(
                            text=(
                                f"⏳ **Limite de requisições Groq atingido.**\n\n"
                                f"Aguarde **{wait_str}** e tente novamente.\n\n"
                                f"*Dica: perguntas repetidas são respondidas do cache sem consumir tokens.*"
                            ),
                            error=err_str,
                        )
                    else:
                        result = AgentResponse(text="Erro ao conectar ao agente IA. Tente novamente.", error=err_str)
                    return result

            if resp is None:
                return AgentResponse(text="Erro ao conectar ao agente IA. Tente novamente.", error="no response")

            if resp.usage:
                tokens_used += resp.usage.total_tokens
            choice = resp.choices[0]

            if choice.finish_reason == "tool_calls":
                tool_msgs = []
                for tc in choice.message.tool_calls:
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
                messages.append(choice.message)
                messages.extend(tool_msgs)
                continue

            text = choice.message.content or ""
            self._history.append({"role": "assistant", "content": text})
            result = AgentResponse(text=text, tool_calls_made=tool_calls_made, tokens_used=tokens_used)

            # Só cacheia respostas bem-sucedidas
            if text:
                _cache_set(ck, result)

            return result

        return AgentResponse(
            text="Limite de iterações atingido. Tente reformular a pergunta.",
            tool_calls_made=tool_calls_made,
            tokens_used=tokens_used,
        )

    def reset(self) -> None:
        self._history.clear()

    def _fallback(self, message: str) -> AgentResponse:
        return AgentResponse(
            text=(
                "**Agente IA indisponível**\n\n"
                "Configure `GROQ_API_KEY` no arquivo `.env` para ativar o agente.\n\n"
                "Chave gratuita em: https://console.groq.com\n\n"
                f"*Pergunta recebida:* {message}"
            ),
            error="GROQ_API_KEY not configured",
        )


def create_agent(year: int = 2024) -> PharmaAgent:
    """Create a PharmaAgent from environment configuration."""
    return PharmaAgent(year=year)
