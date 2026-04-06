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

import json
import logging
import os
import re
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
GROQ_MODEL    = "llama-3.3-70b-versatile"
MAX_ITERATIONS = 6
MAX_HISTORY    = 20

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

        self._history.append({"role": "user", "content": message})
        if len(self._history) > MAX_HISTORY * 2:
            self._history = self._history[-MAX_HISTORY * 2:]

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self._history
        tool_calls_made: list[str] = []
        tokens_used = 0

        for _ in range(MAX_ITERATIONS):
            try:
                resp = self._client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=2048,
                )
            except Exception as exc:
                err_str = str(exc)
                logger.error("Groq API error: %s", err_str)
                # Parse wait time from rate-limit message for a user-friendly response
                wait_match = re.search(r"Please try again in ([\d]+m[\d.]+s|[\d.]+s)", err_str)
                wait_str = wait_match.group(1) if wait_match else "alguns minutos"
                if "rate_limit_exceeded" in err_str or "429" in err_str:
                    return AgentResponse(
                        text=(
                            f"**Limite diário de tokens Groq atingido.**\n\n"
                            f"O plano gratuito permite 100.000 tokens/dia. "
                            f"Tente novamente em **{wait_str}**.\n\n"
                            f"Para uso ilimitado, faça upgrade em: https://console.groq.com/settings/billing"
                        ),
                        error=err_str,
                    )
                return AgentResponse(text="", error=err_str)

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
            return AgentResponse(text=text, tool_calls_made=tool_calls_made, tokens_used=tokens_used)

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
