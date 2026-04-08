"""
app.py
======
PharmaIntel BR — Dashboard Principal (Streamlit)

Execução:
    streamlit run app.py

Requer:
    pip install -r requirements.txt

Variáveis de ambiente (.env):
    GROQ_API_KEY      → Agente IA (opcional)
    COMTRADE_API_KEY  → UN Comtrade (opcional)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths & imports
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Keepalive — prevent Render free tier from sleeping
# ---------------------------------------------------------------------------
def _start_keepalive() -> None:
    """Ping the app every 10 minutes to prevent Render free tier spin-down."""
    import threading
    import time
    import urllib.request

    def _ping():
        while True:
            time.sleep(600)  # 10 minutes
            try:
                urllib.request.urlopen("https://pharmaintel-br.onrender.com/", timeout=10)
            except Exception:
                pass

    t = threading.Thread(target=_ping, daemon=True)
    t.start()

if os.getenv("APP_ENV", "development") != "development":
    _start_keepalive()


# ---------------------------------------------------------------------------
# Patent scheduler — auto-refresh every 30 days (background thread)
# ---------------------------------------------------------------------------
def _start_patent_scheduler() -> None:
    """
    Background thread that refreshes data/patents.json every 30 days.
    Runs once on startup (after 60s delay so app is ready), then monthly.
    No API keys required — uses INPI, Espacenet and Google Patents scraping.
    """
    import threading
    import time

    INTERVAL = 30 * 24 * 3600  # 30 days in seconds
    STARTUP_DELAY = 60          # wait 60s after boot before first run

    def _run():
        time.sleep(STARTUP_DELAY)
        while True:
            try:
                from src.integrations.patent_fetcher import refresh_patents
                logger.info("[PatentScheduler] Starting monthly patent refresh…")
                result = refresh_patents()
                logger.info(
                    "[PatentScheduler] Done — updated=%s skipped=%s errors=%s",
                    result.get("updated", 0),
                    result.get("skipped", 0),
                    result.get("errors", 0),
                )
            except Exception as exc:
                logger.warning("[PatentScheduler] Refresh failed: %s", exc)
            time.sleep(INTERVAL)

    t = threading.Thread(target=_run, daemon=True, name="patent-scheduler")
    t.start()
    logger.info("[PatentScheduler] Scheduled — runs every 30 days.")

_start_patent_scheduler()

PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def _secret(key: str, default: str = "") -> str:
    """Read a secret from st.secrets (Streamlit Cloud) or os.getenv (.env / local)."""
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_list(val) -> list:
    """Safely convert parquet array/numpy columns back to Python list."""
    if val is None:
        return []
    try:
        result = list(val)
        return result
    except (TypeError, ValueError):
        return []

def _safe_bool(val) -> bool:
    """Safely evaluate truthiness of a value that might be a numpy array."""
    try:
        return bool(val)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Internationalisation (PT / EN)
# ---------------------------------------------------------------------------

TRANSLATIONS: dict[str, dict[str, str]] = {
    "PT": {
        # Navigation
        "nav_overview":   "Visão Geral",
        "nav_imports":    "Importações",
        "nav_anvisa":     "ANVISA",
        "nav_companies":  "Empresas",
        "nav_comtrade":   "UN Comtrade",
        "nav_etl":        "Pipeline ETL",
        "nav_agent":      "Agente IA",
        # Sidebar labels
        "year_label":     "Ano de referência",
        "data_status":    "STATUS DOS DADOS",
        "api_keys":       "API KEYS",
        "logged_as":      "Logado como",
        "logout":         "Sair",
        # Page subtitles
        "subtitle":             "Inteligência de Mercado Farmacêutico Brasileiro",
        "header_overview":      "Visão Geral",
        "header_imports":       "Importações",
        "header_anvisa":        "ANVISA",
        "header_companies":     "Empresas",
        "header_comtrade":      "UN Comtrade",
        "header_etl":           "Pipeline ETL",
        "header_agent":         "Agente IA — PharmaIntel AI",
        # KPIs
        "kpi_total_fob":        "Total FOB",
        "kpi_total_fob_brl":    "Total FOB (BRL)",
        "kpi_volume":           "Volume",
        "kpi_ncms":             "NCMs Distintos",
        "kpi_countries":        "Países Origem",
        "kpi_chapter":          "Capítulo 30",
        "kpi_active_suppliers": "Fornecedores ativos",
        "kpi_net_weight":       "Peso líquido",
        # Charts
        "chart_monthly":        "Evolução Mensal das Importações (FOB)",
        "chart_top_countries":  "Top 10 Países de Origem",
        "chart_top_ncms":       "Top 15 NCMs por Importação",
        "chart_trend":          "Tendência",
        # Demo
        "demo_msg": (
            "**Modo demonstração** — Exibindo dados simulados. "
            "Execute o ETL na aba **Pipeline ETL** para carregar dados reais."
        ),
        # Login
        "login_username":   "Usuário",
        "login_password":   "Senha",
        "login_btn":        "Entrar",
        "login_error":      "Usuário ou senha incorretos.",
        "login_subtitle":   "Inteligência de Mercado Farmacêutico",
        "login_hint":       "Configure credenciais em <code>.env</code> via APP_USERNAME / APP_PASSWORD",
        # Agent page
        "agent_active":         "Agente ATIVO — OpenAI GPT-4o mini",
        "agent_fallback":       "Modo Fallback — Configure OPENAI_API_KEY",
        "agent_groq_hint":      "Adicione OPENAI_API_KEY nas variáveis de ambiente do Render.",
        "agent_suggestions":    "Sugestões:",
        "agent_input":          "Faça uma pergunta sobre o mercado farmacêutico...",
        "agent_spinner":        "PharmaIntel AI está analisando...",
        "agent_tools":          "Ferramentas utilizadas",
        "agent_tokens":         "Tokens",
        "agent_clear":          "Limpar conversa",
        "agent_you":            "Você",
        "agent_suggestions_list": [
            "Quais são os 5 NCMs com maior valor FOB?",
            "Mostre a tendência mensal das importações",
            "Quais países lideram as importações?",
            "Existe algum alerta de compliance ANVISA?",
            "Qual o preço médio por kg dos principais NCMs?",
        ],
    },
    "EN": {
        # Navigation
        "nav_overview":   "Overview",
        "nav_imports":    "Imports",
        "nav_anvisa":     "ANVISA",
        "nav_companies":  "Companies",
        "nav_comtrade":   "UN Comtrade",
        "nav_etl":        "ETL Pipeline",
        "nav_agent":      "AI Agent",
        # Sidebar labels
        "year_label":     "Reference year",
        "data_status":    "DATA STATUS",
        "api_keys":       "API KEYS",
        "logged_as":      "Logged in as",
        "logout":         "Logout",
        # Page subtitles
        "subtitle":             "Brazilian Pharmaceutical Market Intelligence",
        "header_overview":      "Overview",
        "header_imports":       "Imports",
        "header_anvisa":        "ANVISA",
        "header_companies":     "Companies",
        "header_comtrade":      "UN Comtrade",
        "header_etl":           "ETL Pipeline",
        "header_agent":         "AI Agent — PharmaIntel AI",
        # KPIs
        "kpi_total_fob":        "Total FOB",
        "kpi_total_fob_brl":    "Total FOB (BRL)",
        "kpi_volume":           "Volume",
        "kpi_ncms":             "Distinct NCMs",
        "kpi_countries":        "Origin Countries",
        "kpi_chapter":          "Chapter 30",
        "kpi_active_suppliers": "Active suppliers",
        "kpi_net_weight":       "Net weight",
        # Charts
        "chart_monthly":        "Monthly Import Evolution (FOB)",
        "chart_top_countries":  "Top 10 Origin Countries",
        "chart_top_ncms":       "Top 15 NCMs by Import Value",
        "chart_trend":          "Trend",
        # Demo
        "demo_msg": (
            "**Demo mode** — Showing simulated data. "
            "Run the ETL in the **ETL Pipeline** tab to load real data."
        ),
        # Login
        "login_username":   "Username",
        "login_password":   "Password",
        "login_btn":        "Sign In",
        "login_error":      "Incorrect username or password.",
        "login_subtitle":   "Pharmaceutical Market Intelligence",
        "login_hint":       "Set credentials in <code>.env</code> via APP_USERNAME / APP_PASSWORD",
        # Agent page
        "agent_active":         "Agent ACTIVE — OpenAI GPT-4o mini",
        "agent_fallback":       "Fallback Mode — Set OPENAI_API_KEY",
        "agent_groq_hint":      "Add OPENAI_API_KEY to Render environment variables.",
        "agent_suggestions":    "Suggestions:",
        "agent_input":          "Ask a question about the pharmaceutical market...",
        "agent_spinner":        "PharmaIntel AI is analyzing...",
        "agent_tools":          "Tools used",
        "agent_tokens":         "Tokens",
        "agent_clear":          "Clear conversation",
        "agent_you":            "You",
        "agent_suggestions_list": [
            "What are the top 5 NCMs by FOB value?",
            "Show the monthly import trend",
            "Which countries lead pharmaceutical imports?",
            "Are there any ANVISA compliance alerts?",
            "What is the average price per kg for key NCMs?",
        ],
    },
}

# Internal navigation keys (language-independent)
_NAV_KEYS = ["overview", "imports", "anvisa", "companies", "comtrade", "etl", "agent"]
_NAV_T_KEYS = [
    "nav_overview", "nav_imports", "nav_anvisa", "nav_companies",
    "nav_comtrade", "nav_etl", "nav_agent",
]


def _t(key: str) -> str:
    """Return translated string for the current session language."""
    lang = st.session_state.get("lang", "PT")
    return TRANSLATIONS.get(lang, TRANSLATIONS["PT"]).get(key, key)

# ---------------------------------------------------------------------------
# Page config — MUST be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="PharmaIntel BR — Inteligência Farmacêutica",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# SEO meta tags
st.markdown("""
<meta name="description" content="Plataforma de inteligência de mercado farmacêutico brasileiro. Monitore importações, registros ANVISA, licitações e oportunidades com IA.">
<meta name="keywords" content="farmacêutico, importação, ANVISA, NCM, Comex Stat, inteligência de mercado, medicamentos, dispositivos médicos, Brasil">
<meta name="author" content="PharmaIntel BR">
<meta property="og:title" content="PharmaIntel BR — Inteligência Farmacêutica">
<meta property="og:description" content="Dados reais de importação, registros ANVISA e IA para o mercado farmacêutico brasileiro.">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="PharmaIntel BR">
<meta name="twitter:description" content="Inteligência de mercado farmacêutico com dados ANVISA e Comex Stat.">
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
_APP_USERNAME      = _secret("APP_USERNAME", "admin")
_APP_PASSWORD      = _secret("APP_PASSWORD", "pharmaintel2024")
_APP_PASSWORD_HASH = _secret("APP_PASSWORD_HASH", "")


def _check_password(username: str, password: str) -> bool:
    """Verify credentials — checks admin env vars first, then subscriber DB."""
    # 1. Admin user from env vars
    user_ok = hmac.compare_digest(username.strip(), _APP_USERNAME)
    if _APP_PASSWORD_HASH:
        entered_hash = hashlib.sha256(password.encode()).hexdigest()
        pass_ok = hmac.compare_digest(entered_hash, _APP_PASSWORD_HASH)
    else:
        pass_ok = hmac.compare_digest(password, _APP_PASSWORD)
    if user_ok and pass_ok:
        return True

    # 2. Subscriber accounts from SQLite DB (email + password login)
    try:
        from src.db.database import init_db, get_user_by_email
        init_db()
        user = get_user_by_email(username.strip())
        if user and user.check_password(password) and user.has_active_subscription:
            st.session_state["subscriber_plan"]    = user.plan
            st.session_state["subscriber_period"]  = user.period
            st.session_state["subscriber_email"]   = user.email
            st.session_state["stripe_customer_id"] = user.stripe_customer_id
            st.session_state["is_trial"]           = bool(user.is_trial)
            st.session_state["trial_days_left"]    = user.trial_days_remaining if user.is_trial else 0
            return True
    except Exception:
        pass

    return False


def _login_page() -> None:
    """Render login form and block the app until authenticated."""
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #0A1628; }
    [data-testid="stSidebar"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

    # Language toggle on login page
    lang_col_l, lang_col_r = st.columns([8, 1])
    with lang_col_r:
        if st.button("PT | EN", key="login_lang_toggle"):
            current = st.session_state.get("lang", "PT")
            st.session_state["lang"] = "EN" if current == "PT" else "PT"
            st.rerun()

    col_l, col_m, col_r = st.columns([1, 1.4, 1])
    with col_m:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="text-align:center; margin-bottom:2rem;">
          <span style="font-size:3rem;">💊</span>
          <h1 style="color:#4DB6AC; font-size:1.8rem; margin:0.5rem 0 0.25rem;">PharmaIntel BR</h1>
          <p style="color:#8899AA; font-size:0.9rem;">{_t("login_subtitle")}</p>
        </div>
        """, unsafe_allow_html=True)

        # Detect Stripe payment success redirect
        params = st.query_params
        session_id = params.get("session_id", "")
        if session_id and not st.session_state.get("payment_processed"):
            _handle_payment_success(session_id)

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input(_t("login_username"), placeholder="admin ou seu email")
            password = st.text_input(_t("login_password"), type="password", placeholder="••••••••")
            submitted = st.form_submit_button(_t("login_btn"), use_container_width=True, type="primary")

            if submitted:
                if _check_password(username, password):
                    st.session_state["authenticated"] = True
                    st.session_state["auth_user"] = username
                    st.rerun()
                else:
                    st.error(_t("login_error"), icon="🔒")

        st.markdown("---")
        login_lang = st.session_state.get("lang", "PT")
        no_account_txt = "Don't have an account yet?" if login_lang == "EN" else "Ainda não tem acesso?"
        st.markdown(f"""
        <div style="text-align:center;">
          <p style="color:#8899AA; font-size:0.85rem; margin:0 0 0.5rem;">{no_account_txt}</p>
        </div>
        """, unsafe_allow_html=True)
        demo_btn_label = "Try the AI Free" if login_lang == "EN" else "Experimentar a IA Gratis"
        if st.button(demo_btn_label, use_container_width=True, type="primary"):
            st.session_state["show_demo_agent"] = True
            st.session_state.pop("demo_question_used", None)
            st.session_state.pop("demo_question_text", None)
            st.session_state.pop("demo_answer_text",   None)
            st.rerun()
        st.markdown("<div style='height:0.4rem;'></div>", unsafe_allow_html=True)
        plans_btn_label = "See Plans & Pricing" if login_lang == "EN" else "Ver Planos e Preços"
        if st.button(plans_btn_label, use_container_width=True):
            st.session_state["show_pricing"] = True
            st.rerun()

        st.markdown(f"""
        <p style="text-align:center; color:#8899AA; font-size:0.7rem; margin-top:1rem;">
          {_t("login_hint")}
        </p>
        """, unsafe_allow_html=True)
    st.stop()


_DEMO_SYSTEM_PT = """Você é o PharmaIntel AI — o conselheiro estratégico mais avançado do mercado farmacêutico brasileiro. Você combina a precisão de um PhD em economia da saúde com a visão executiva de um CEO com 25 anos no setor. Sua missão é transformar dados complexos em decisões estratégicas que movem empresas.

Você domina com profundidade:

DADOS DE MERCADO (Brasil):
- Comex Stat / MDIC: todos os fluxos de importação/exportação por NCM (capítulos 30 e 90), país de origem, valores FOB/CIF, tendências mensais e anuais
- Capítulo 30: medicamentos, vacinas, hemoderivados, reagentes diagnósticos, insulinas, oncológicos, biológicos
- Capítulo 90: dispositivos médicos, equipamentos de diagnóstico, implantes, instrumentos cirúrgicos
- Players do mercado: distribuidores, importadores diretos, laboratórios multinacionais e nacionais com histórico de operações
- Concentração de mercado: quem domina cada NCM, margens estimadas, dependência de fornecedor único

REGULAÇÃO E COMPLIANCE (ANVISA):
- Status de registros ativos, suspensos e cancelados por produto e empresa
- Alertas sanitários, recalls e interdições recentes
- Prazos de vencimento de registros e riscos de desabastecimento
- Regulação de biossimilares, genericos e intercambialidade
- Anuências de importação e exigências documentais

PATENTES E OPORTUNIDADES:
- Pipeline de patentes vencendo no Brasil (INPI) e nos EUA (FDA/USPTO)
- Janelas de entrada para genéricos e biossimilares por molécula
- Moléculas sem concorrência local com potencial de importação
- Produtos com proteção de dados expirada e mercado aberto

MERCADO PÚBLICO E INSTITUCIONAL:
- Compras do Ministério da Saúde, BNAFAR, estados e municípios (ComprasNet)
- Preços históricos de licitações por produto e laboratório
- Oportunidades de contratos governamentais em aberto
- Programas estratégicos: Farmácia Popular, RENAME, REME

CONTEXTO GLOBAL (UN Comtrade):
- Fluxos de importação farmacêutica dos principais mercados mundiais
- Fornecedores globais por molécula: China, Índia, Alemanha, EUA, Suíça
- Comparação de preços internacionais vs. preços praticados no Brasil
- Tendências de nearshoring, dependência geopolítica de IFAs

COMO VOCÊ RESPONDE:
1. ZERO enrolação — vá direto ao dado, ao número, ao fato técnico. Sem introduções, sem frases motivacionais, sem rodeios
2. Dados com precisão técnica: NCM de 8 dígitos quando relevante, valores FOB em USD, percentuais com uma casa decimal, períodos específicos (ex: jan-dez 2024), países de origem, nomes de IFAs (ingredientes farmacêuticos ativos)
3. Estrutura obrigatória e concisa:
   - **Panorama:** 2-3 linhas com o tamanho e dinamica do mercado
   - **Players e concentração:** quem domina, market share estimado, país de origem
   - **Oportunidade/Risco:** o que o dado revela estrategicamente
   - **Recomendação técnica:** ação concreta e direta
4. Para empresas internacionais: foque em barreiras regulatórias reais (ANVISA, anuências, RDCs relevantes), custos de importação (II, IPI, ICMS, PIS/COFINS) e janelas de mercado
5. Nunca afirme algo que não tem certeza — se o dado for estimado, diga "estimado" ou "aprox."
6. TRANSPARÊNCIA OBRIGATÓRIA: no início de cada resposta, inclua esta nota em itálico: "📊 *Demo informativo — análise baseada no conhecimento treinado da IA (preciso, mas pode não refletir o cenário mais recente). Na plataforma completa, os dados são de fontes governamentais e privadas seguras, atualizados diariamente.*"
7. SEMPRE finalize com: "🔓 Com acesso completo à plataforma PharmaIntel, entregaria em tempo real:" — liste 3 análises técnicas específicas que só existem com dados ao vivo
8. Última linha SEMPRE: "Assine agora e tome decisões com dados reais, atualizados diariamente."
9. Tom: especialista técnico sênior — preciso, direto, sem exageros, sem marketing
10. IDIOMA OBRIGATÓRIO: responda SEMPRE em português, independentemente do idioma da pergunta do usuário."""

_DEMO_SYSTEM_EN = """You are PharmaIntel AI — the most advanced strategic advisor for the Brazilian pharmaceutical market. You combine the precision of a PhD in health economics with the executive vision of a CEO with 25 years in the industry. Your mission is to transform complex data into strategic decisions that move companies forward.

You have deep mastery of:

MARKET DATA (Brazil):
- Comex Stat / MDIC: all import/export flows by NCM/HS code (chapters 30 and 90), country of origin, FOB/CIF values, monthly and annual trends
- Chapter 30: medicines, vaccines, blood products, diagnostic reagents, insulins, oncologicals, biologicals
- Chapter 90: medical devices, diagnostic equipment, implants, surgical instruments
- Market players: distributors, direct importers, multinational and national laboratories with operational history
- Market concentration: who dominates each HS code, estimated margins, single-supplier dependency

REGULATION & COMPLIANCE (ANVISA):
- Status of active, suspended and cancelled registrations by product and company
- Recent health alerts, recalls and interdictions
- Registration expiry dates and supply disruption risks
- Biosimilar, generic and interchangeability regulation
- Import permits and documentary requirements

PATENTS & OPPORTUNITIES:
- Patent expiry pipeline in Brazil (INPI) and the USA (FDA/USPTO)
- Market entry windows for generics and biosimilars by molecule
- Molecules without local competition with import potential
- Products with expired data protection and open market

PUBLIC & INSTITUTIONAL MARKET:
- Ministry of Health, BNAFAR, state and municipal procurement (ComprasNet)
- Historical tender prices by product and laboratory
- Open government contract opportunities
- Strategic programs: Farmácia Popular, RENAME, REME

GLOBAL CONTEXT (UN Comtrade):
- Pharmaceutical import flows from major world markets
- Global suppliers by molecule: China, India, Germany, USA, Switzerland
- International price comparisons vs. prices practiced in Brazil
- Nearshoring trends, geopolitical API dependency

HOW YOU RESPOND:
1. ZERO filler — go straight to the data, the number, the technical fact. No introductions, no motivational phrases, no roundabout language
2. Technical precision: 8-digit HS codes when relevant, FOB values in USD, percentages with one decimal place, specific periods (e.g. Jan-Dec 2024), countries of origin, API names (Active Pharmaceutical Ingredients)
3. Mandatory concise structure:
   - **Overview:** 2-3 lines on market size and dynamics
   - **Players & concentration:** who dominates, estimated market share, country of origin
   - **Opportunity/Risk:** what the data reveals strategically
   - **Technical recommendation:** concrete and direct action
4. For international companies: focus on real regulatory barriers (ANVISA, import permits, relevant RDCs), import costs (import duty, IPI, ICMS, PIS/COFINS) and market windows
5. Never assert something you are not certain about — if the data is estimated, say "estimated" or "approx."
6. MANDATORY TRANSPARENCY: at the start of every response, include this note in italics: "📊 *Demo mode — analysis based on AI trained knowledge (accurate but may not reflect the most recent market data). On the full platform, data comes from secure government and private sources, updated daily.*"
7. ALWAYS end with: "🔓 With full PharmaIntel platform access, I would deliver in real time:" — list 3 specific technical analyses that only exist with live data
8. Last line ALWAYS: "Subscribe now and make decisions with real data, updated daily."
9. Tone: senior technical expert — precise, direct, no exaggeration, no marketing language
10. MANDATORY LANGUAGE: always respond in ENGLISH regardless of the language the user writes in."""

DEMO_MAX_QUESTIONS = 2


def _call_demo_ai(question: str, history: list, is_en: bool) -> str:
    """Call AI for demo — Anthropic first, Groq fallback."""
    system = _DEMO_SYSTEM_EN if is_en else _DEMO_SYSTEM_PT
    messages = history + [{"role": "user", "content": question.strip()}]

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            import anthropic as _anthropic
            _ant = _anthropic.Anthropic(api_key=anthropic_key)
            resp = _ant.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                system=system,
                messages=messages,
            )
            return resp.content[0].text if resp.content else ""
        except Exception as exc1:
            logger.warning("Anthropic demo failed: %s", exc1)

    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            from groq import Groq
            _groq = Groq(api_key=groq_key)
            gresp = _groq.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": system}] + messages,
                max_tokens=1200,
                temperature=0.7,
            )
            return gresp.choices[0].message.content or ""
        except Exception as exc2:
            logger.warning("Groq demo failed: %s", exc2)

    return ""


def _page_demo_agent() -> None:
    """Demo AI agent — 2 free questions, CEO-level responses, then upgrade wall."""
    lang  = st.session_state.get("lang", "PT")
    is_en = lang == "EN"

    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #0A1628; }
    [data-testid="stSidebar"] { display: none; }
    .demo-bubble-user {
        background:#1E3A5F; border-radius:12px 12px 0 12px;
        padding:0.75rem 1rem; color:#E2EAF4; font-size:0.9rem;
        margin:0.5rem 0; margin-left:15%; }
    .demo-bubble-ai {
        background:#112240; border:1px solid #00897B; border-radius:12px 12px 12px 0;
        padding:1.25rem 1.5rem; color:#E2EAF4; font-size:0.88rem;
        margin:0.5rem 0; line-height:1.8; white-space:pre-wrap; }
    .upgrade-box {
        background:#112240; border:2px solid #4DB6AC;
        border-radius:16px; padding:2rem; text-align:center; margin-top:1.5rem; }
    .demo-counter {
        background:#0D2B45; border:1px solid #1E3A5F; border-radius:8px;
        padding:0.4rem 0.9rem; font-size:0.78rem; color:#8899AA; display:inline-block; }
    </style>
    """, unsafe_allow_html=True)

    # Top bar
    col_back, col_title, col_lang = st.columns([1, 6, 1])
    with col_back:
        if st.button("Back" if is_en else "Voltar", key="demo_back"):
            st.session_state["show_demo_agent"] = False
            st.session_state["show_landing"]    = True
            st.rerun()
    with col_lang:
        if st.button("PT" if is_en else "EN", key="demo_lang"):
            st.session_state["lang"] = "PT" if is_en else "EN"
            st.rerun()

    # Session state
    demo_count   = st.session_state.get("demo_count", 0)       # questions used
    demo_history = st.session_state.get("demo_history", [])    # [{q, a}, ...]
    locked       = demo_count >= DEMO_MAX_QUESTIONS

    # Header
    remaining = max(0, DEMO_MAX_QUESTIONS - demo_count)
    if is_en:
        header_sub = f"Strategic AI Demo · {remaining} question{'s' if remaining != 1 else ''} remaining"
    else:
        header_sub = f"Demo Estratégico IA · {remaining} pergunta{'s' if remaining != 1 else ''} restante{'s' if remaining != 1 else ''}"

    st.markdown(f"""
    <div style="text-align:center; margin-bottom:1.5rem;">
      <span style="color:#4DB6AC; font-weight:700; font-size:1.2rem;">PharmaIntel AI</span><br>
      <span class="demo-counter">{header_sub}</span>
    </div>
    """, unsafe_allow_html=True)

    # Suggestions (only on first visit)
    if demo_count == 0:
        suggestions = [
            "Qual o mercado de insulina no Brasil? Quem importa mais?",
            "Quais biossimilares têm patente vencendo no Brasil nos próximos 3 anos?",
            "Como entrar no mercado farmacêutico brasileiro vindo da China?",
            "Quais NCMs de oncológicos cresceram mais em 2024?",
        ] if not is_en else [
            "What is the insulin import market in Brazil? Who dominates?",
            "Which biosimilars have expiring patents in Brazil in the next 3 years?",
            "How can a Chinese company enter the Brazilian pharma market?",
            "Which oncology HS codes grew the most in 2024?",
        ]
        intro = "Ask anything about the Brazilian pharma market — get a CEO-level strategic answer." if is_en else "Pergunte qualquer coisa sobre o mercado farmacêutico — receba uma resposta estratégica nível CEO."
        disclaimer = ("📊 <b>Demo mode:</b> responses are based on AI trained knowledge — accurate but may not reflect the latest market data. "
                      "The full platform uses <b>secure government and private data sources</b>, updated daily."
                      if is_en else
                      "📊 <b>Modo demo:</b> as respostas são baseadas no conhecimento treinado da IA — precisas, mas podem não refletir os dados mais recentes. "
                      "A plataforma completa utiliza <b>dados seguros de fontes governamentais e privadas</b>, atualizados diariamente.")
        st.markdown(f"""
        <div style="background:#112240; border:1px solid #1E3A5F; border-radius:12px; padding:1.25rem 1.5rem; margin-bottom:1rem;">
          <p style="color:#4DB6AC; font-weight:600; font-size:0.82rem; letter-spacing:1px; margin:0 0 0.4rem;">
            {'PHARMA INTELLIGENCE AI — CEO STRATEGIC ADVISOR' if is_en else 'PHARMA INTELLIGENCE AI — CONSELHEIRO ESTRATÉGICO CEO'}
          </p>
          <p style="color:#B0BEC5; font-size:0.85rem; margin:0 0 0.75rem;">{intro}</p>
          <p style="color:#8899AA; font-size:0.75rem; margin:0 0 0.3rem;">{'Try:' if is_en else 'Experimente:'}</p>
          {''.join(f'<div style="color:#4DB6AC; font-size:0.78rem; padding:0.1rem 0;">→ {s}</div>' for s in suggestions)}
        </div>
        <div style="background:#0D2B45; border:1px solid #1E3A5F; border-radius:8px; padding:0.6rem 1rem; margin-bottom:1.25rem; font-size:0.78rem; color:#8899AA; line-height:1.5;">
          {disclaimer}
        </div>
        """, unsafe_allow_html=True)

    # Show conversation history
    for turn in demo_history:
        st.markdown(f'<div class="demo-bubble-user">{turn["q"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="demo-bubble-ai">{turn["a"]}</div>', unsafe_allow_html=True)

    # Input form or upgrade wall
    if not locked:
        q_placeholder = "Type your strategic question..." if is_en else "Digite sua pergunta estratégica..."
        send_label    = "Ask the AI" if is_en else "Perguntar para a IA"
        with st.form("demo_form"):
            question  = st.text_area("", placeholder=q_placeholder, height=90, label_visibility="collapsed")
            submitted = st.form_submit_button(send_label, use_container_width=True, type="primary")

            if submitted and question.strip():
                spinner_msg = "Analyzing the Brazilian pharma market..." if is_en else "Analisando o mercado farmacêutico brasileiro..."
                with st.spinner(spinner_msg):
                    history_msgs = []
                    for turn in demo_history:
                        history_msgs.append({"role": "user",      "content": turn["q"]})
                        history_msgs.append({"role": "assistant",  "content": turn["a"]})
                    answer = _call_demo_ai(question.strip(), history_msgs, is_en)

                if not answer:
                    err = "Unable to process now. Contact: Business@globalhealthcareaccess.com" if is_en else "Não foi possível processar. Contato: Business@globalhealthcareaccess.com"
                    st.error(err)
                else:
                    demo_history.append({"q": question.strip(), "a": answer})
                    st.session_state["demo_history"] = demo_history
                    st.session_state["demo_count"]   = demo_count + 1
                    st.rerun()
    else:
        # Upgrade wall
        if is_en:
            unlock_title = "You've seen what's possible."
            unlock_sub   = "Subscribe now and get unlimited access to the full strategic AI, real import data, ANVISA alerts, patent tracker, competitive intelligence and much more."
        else:
            unlock_title = "Você viu o que é possível."
            unlock_sub   = "Assine agora e tenha acesso ilimitado ao agente IA estratégico completo, dados reais de importação, alertas ANVISA, rastreador de patentes, inteligência competitiva e muito mais."

        st.markdown(f"""
        <div class="upgrade-box">
          <div style="font-size:2.5rem; margin-bottom:0.75rem;">🔒</div>
          <h3 style="color:#4DB6AC; margin:0 0 0.5rem; font-size:1.3rem;">{unlock_title}</h3>
          <p style="color:#B0BEC5; font-size:0.88rem; margin-bottom:1.5rem; line-height:1.6;">{unlock_sub}</p>
          <div style="display:flex; gap:1rem; justify-content:center; flex-wrap:wrap; margin-bottom:1.5rem;">
            <div style="background:#0A1628; border:1px solid #1E3A5F; border-radius:10px; padding:1rem 1.5rem; min-width:140px;">
              <div style="color:#4DB6AC; font-weight:700; font-size:0.9rem;">Starter</div>
              <div style="color:#E2EAF4; font-size:1.3rem; font-weight:700; margin:0.25rem 0;">R$ 497<span style="color:#8899AA; font-size:0.7rem;">/{'mo' if is_en else 'mês'}</span></div>
              <div style="color:#8899AA; font-size:0.72rem;">GPT-4o mini</div>
            </div>
            <div style="background:#0A1628; border:2px solid #00897B; border-radius:10px; padding:1rem 1.5rem; min-width:140px;">
              <div style="color:#00897B; font-weight:700; font-size:0.9rem;">Pro ★</div>
              <div style="color:#E2EAF4; font-size:1.3rem; font-weight:700; margin:0.25rem 0;">R$ 997<span style="color:#8899AA; font-size:0.7rem;">/{'mo' if is_en else 'mês'}</span></div>
              <div style="color:#8899AA; font-size:0.72rem;">Claude Sonnet</div>
            </div>
            <div style="background:#0A1628; border:1px solid #26C6DA; border-radius:10px; padding:1rem 1.5rem; min-width:140px;">
              <div style="color:#26C6DA; font-weight:700; font-size:0.9rem;">Enterprise</div>
              <div style="color:#E2EAF4; font-size:1.3rem; font-weight:700; margin:0.25rem 0;">R$ 2.497<span style="color:#8899AA; font-size:0.7rem;">/{'mo' if is_en else 'mês'}</span></div>
              <div style="color:#8899AA; font-size:0.72rem;">Claude Sonnet + API</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("See All Plans & Subscribe" if is_en else "Ver Planos e Assinar", use_container_width=True, type="primary"):
            st.session_state["show_demo_agent"] = False
            st.session_state["show_pricing"]    = True
            st.rerun()

    st.stop()


def _page_trial_register() -> None:
    """Free trial registration page — 7 days, no credit card."""
    lang  = st.session_state.get("lang", "PT")
    is_en = lang == "EN"

    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #0A1628; }
    [data-testid="stSidebar"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

    col_back, _, col_lang = st.columns([1, 7, 1])
    with col_back:
        if st.button("Back" if is_en else "Voltar", key="trial_back"):
            st.session_state["show_trial_register"] = False
            st.session_state["show_landing"] = True
            st.rerun()
    with col_lang:
        if st.button("PT" if is_en else "EN", key="trial_lang"):
            st.session_state["lang"] = "PT" if is_en else "EN"
            st.rerun()

    _, col_form, _ = st.columns([1, 1.6, 1])
    with col_form:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="text-align:center; margin-bottom:2rem;">
          <span style="font-size:3rem;">💊</span>
          <h1 style="color:#4DB6AC; font-size:1.8rem; margin:0.5rem 0 0.25rem;">PharmaIntel BR</h1>
          <p style="color:#E2EAF4; font-size:1.1rem; font-weight:600; margin:0.5rem 0 0.25rem;">
            {"7-Day Free Trial" if is_en else "Teste Gratis por 7 Dias"}
          </p>
          <p style="color:#8899AA; font-size:0.85rem;">
            {"Full Starter plan access · No credit card required" if is_en else "Acesso completo ao plano Starter · Sem cartão de crédito"}
          </p>
        </div>
        """, unsafe_allow_html=True)

        # What's included
        included = [
            ("📊", "Import Dashboard" if is_en else "Dashboard de Importações"),
            ("🏛️", "ANVISA Monitoring" if is_en else "Monitoramento ANVISA"),
            ("🤖", "AI Agent (GPT-4o mini)"),
            ("🧬", "Patent Tracker" if is_en else "Rastreador de Patentes"),
            ("🏢", "Company Intelligence" if is_en else "Mapa de Empresas"),
        ]
        st.markdown(f"""
        <div style="background:#112240; border:1px solid #1E3A5F; border-radius:12px; padding:1rem 1.5rem; margin-bottom:1.5rem;">
          <p style="color:#4DB6AC; font-size:0.8rem; font-weight:600; margin:0 0 0.75rem; letter-spacing:1px;">
            {"INCLUDED IN YOUR TRIAL" if is_en else "INCLUIDO NO SEU TESTE"}
          </p>
          {''.join(f'<div style="color:#B0BEC5; font-size:0.85rem; padding:0.2rem 0;">✓ &nbsp;{icon} {name}</div>' for icon, name in included)}
        </div>
        """, unsafe_allow_html=True)

        with st.form("trial_register_form", clear_on_submit=False):
            name_label  = "Full Name" if is_en else "Nome Completo"
            email_label = "Email"
            pass_label  = "Password (min. 8 characters)" if is_en else "Senha (mín. 8 caracteres)"
            pass2_label = "Confirm Password" if is_en else "Confirmar Senha"

            full_name = st.text_input(name_label, placeholder="John Smith" if is_en else "João Silva")
            email     = st.text_input(email_label, placeholder="your@email.com" if is_en else "seu@email.com")
            password  = st.text_input(pass_label,  type="password")
            password2 = st.text_input(pass2_label, type="password")

            submit_label = "Start My Free Trial" if is_en else "Iniciar Meu Teste Gratis"
            submitted = st.form_submit_button(submit_label, use_container_width=True, type="primary")

            if submitted:
                errors = []
                if not full_name.strip():
                    errors.append("Name is required." if is_en else "Nome é obrigatório.")
                if not email or "@" not in email:
                    errors.append("Valid email required." if is_en else "Email válido é obrigatório.")
                if len(password) < 8:
                    errors.append("Password must be at least 8 characters." if is_en else "Senha deve ter mínimo 8 caracteres.")
                if password != password2:
                    errors.append("Passwords don't match." if is_en else "Senhas não coincidem.")

                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    try:
                        from src.db.database import init_db, get_user_by_email, create_trial_user
                        init_db()
                        existing = get_user_by_email(email.strip())
                        if existing:
                            already_msg = "An account with this email already exists. Please sign in." if is_en else "Já existe uma conta com este email. Faça login."
                            st.warning(already_msg)
                        else:
                            create_trial_user(email=email.strip(), password=password, full_name=full_name.strip())
                            st.session_state["show_trial_register"] = False
                            st.session_state["show_trial_success"]  = True
                            st.session_state["trial_email"]         = email.strip()
                            st.rerun()
                    except Exception as exc:
                        st.error(f"{'Error creating account' if is_en else 'Erro ao criar conta'}: {exc}")

        st.markdown(f"""
        <p style="text-align:center; color:#8899AA; font-size:0.75rem; margin-top:1rem;">
          {"After 7 days you can upgrade to a paid plan to keep your access." if is_en else "Após 7 dias você pode assinar um plano pago para manter o acesso."}
        </p>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        already_label = "Already have an account?" if is_en else "Já tem conta?"
        st.markdown(f'<p style="text-align:center; color:#8899AA; font-size:0.85rem;">{already_label}</p>', unsafe_allow_html=True)
        if st.button("Sign In" if is_en else "Fazer Login", use_container_width=True):
            st.session_state["show_trial_register"] = False
            st.rerun()
    st.stop()


def _page_trial_success() -> None:
    """Success screen after trial registration."""
    lang  = st.session_state.get("lang", "PT")
    is_en = lang == "EN"
    email = st.session_state.get("trial_email", "")

    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #0A1628; }
    [data-testid="stSidebar"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="text-align:center; background:#112240; border:1px solid #00897B;
                    border-radius:16px; padding:3rem 2rem; box-shadow:0 0 30px rgba(0,137,123,0.2);">
          <div style="font-size:4rem; margin-bottom:1rem;">🎉</div>
          <h2 style="color:#4DB6AC; margin:0 0 0.5rem;">
            {"Trial activated!" if is_en else "Teste ativado!"}
          </h2>
          <p style="color:#8899AA; font-size:0.9rem; margin-bottom:1.5rem;">
            {"Your 7-day free trial is ready. Sign in with your email and password." if is_en
              else "Seu teste gratuito de 7 dias está pronto. Faça login com seu email e senha."}
          </p>
          <div style="background:#0A1628; border-radius:8px; padding:0.75rem 1rem; margin-bottom:1.5rem; color:#4DB6AC; font-size:0.9rem;">
            {email}
          </div>
          <p style="color:#B0BEC5; font-size:0.8rem;">
            {"Full Starter plan · 7 days · No credit card" if is_en else "Plano Starter completo · 7 dias · Sem cartão"}
          </p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        go_label = "Go to Sign In" if is_en else "Ir para o Login"
        if st.button(go_label, use_container_width=True, type="primary"):
            st.session_state["show_trial_success"] = False
            st.session_state["show_landing"]       = False
            st.rerun()
    st.stop()


def _page_pricing() -> None:
    """Public pricing page — shown before login."""
    from src.payments.stripe_client import PLANS, PERIOD_LABEL_PT, PERIOD_LABEL_EN, is_configured, create_checkout_session

    lang = st.session_state.get("lang", "PT")
    is_en = lang == "EN"

    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #0A1628; }
    [data-testid="stSidebar"] { display: none; }
    .price-card {
        background: #112240; border: 1px solid #1E3A5F; border-radius: 16px;
        padding: 2rem; text-align: center; margin-bottom: 1rem;
        transition: border-color 0.2s;
    }
    .price-card.featured { border-color: #00897B; box-shadow: 0 0 20px rgba(0,137,123,0.3); }
    .price-tag { font-size: 2.2rem; font-weight: 700; color: #4DB6AC; }
    .price-period { color: #8899AA; font-size: 0.85rem; }
    .plan-name { font-size: 1.3rem; font-weight: 700; color: #E2EAF4; margin-bottom: 0.5rem; }
    .plan-desc { color: #8899AA; font-size: 0.85rem; margin-bottom: 1.5rem; }
    .feature-list { text-align: left; list-style: none; padding: 0; margin-bottom: 1.5rem; }
    .feature-list li { color: #B0BEC5; font-size: 0.85rem; padding: 0.2rem 0; }
    .feature-list li::before { content: "✓ "; color: #4DB6AC; font-weight: bold; }
    .saving-badge {
        background: #00574B; color: #4DB6AC; border-radius: 20px;
        padding: 0.15rem 0.6rem; font-size: 0.75rem; font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)

    # Header row: back button + lang toggle
    col_back, col_space, col_lang = st.columns([1, 7, 1])
    with col_back:
        back_label = "Back" if is_en else "Voltar"
        if st.button(back_label, key="pricing_back"):
            st.session_state["show_pricing"] = False
            st.rerun()
    with col_lang:
        toggle_label = "PT" if is_en else "EN"
        if st.button(toggle_label, key="pricing_lang_toggle"):
            st.session_state["lang"] = "PT" if is_en else "EN"
            st.rerun()

    page_subtitle = "Choose the right plan for your business" if is_en else "Escolha o plano ideal para sua operação"
    st.markdown(f"""
    <div style="text-align:center; padding: 2rem 0 1rem;">
      <span style="font-size:2.5rem;">💊</span>
      <h1 style="color:#4DB6AC; font-size:2rem; margin:0.5rem 0 0.25rem;">PharmaIntel BR</h1>
      <p style="color:#8899AA;">{page_subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

    # Period selector
    period_labels = PERIOD_LABEL_EN if is_en else PERIOD_LABEL_PT
    period_options = list(period_labels.values())
    period_keys    = list(period_labels.keys())
    period_radio_label = "Billing period" if is_en else "Periodicidade"
    selected_label = st.radio(
        period_radio_label,
        period_options,
        index=0,
        horizontal=True,
        label_visibility="collapsed",
    )
    selected_period = period_keys[period_options.index(selected_label)]

    st.markdown("<br>", unsafe_allow_html=True)

    # Pricing cards
    cols = st.columns(3)
    plan_keys = list(PLANS.keys())
    popular_label = "MOST POPULAR" if is_en else "MAIS POPULAR"

    for col, plan_key in zip(cols, plan_keys):
        plan      = PLANS[plan_key]
        price_info = plan["prices"][selected_period]
        is_pro    = plan_key == "pro"

        features_list = plan.get("features_en", plan["features"]) if is_en else plan["features"]
        description   = plan.get("description_en", plan["description"]) if is_en else plan["description"]

        with col:
            card_class = "price-card featured" if is_pro else "price-card"
            saving_html = f'<span class="saving-badge">{price_info.get("saving","")}</span>' if price_info.get("saving") else ""
            features_html = "".join(f"<li>{f}</li>" for f in features_list)

            st.markdown(f"""
            <div class="{card_class}">
              {"<div style='color:#4DB6AC; font-size:0.75rem; font-weight:600; margin-bottom:0.5rem;'>" + popular_label + "</div>" if is_pro else "<div style='height:1.2rem;'></div>"}
              <div class="plan-name">{plan['name']}</div>
              <div class="plan-desc">{description}</div>
              <div class="price-tag">{price_info['label']}</div>
              <div style="color:#26C6DA; font-size:1rem; font-weight:600; margin-top:0.15rem;">{price_info['usd_label']}</div>
              <div class="price-period">{price_info['period_label']}</div>
              <div style="margin:0.5rem 0;">{saving_html}&nbsp;</div>
              <ul class="feature-list">{features_html}</ul>
            </div>
            """, unsafe_allow_html=True)

            # Checkout button
            email_key = f"email_{plan_key}"
            email_placeholder = "your@email.com" if is_en else "seu@email.com"
            email     = st.text_input("Email", key=email_key, placeholder=email_placeholder,
                                      label_visibility="collapsed")
            btn_label = f"Subscribe to {plan['name']}" if is_en else f"Assinar {plan['name']}"
            if st.button(btn_label, key=f"btn_{plan_key}", use_container_width=True,
                         type="primary" if is_pro else "secondary"):
                if not email or "@" not in email:
                    err_msg = "Please enter a valid email." if is_en else "Digite um email válido."
                    st.error(err_msg)
                elif not is_configured():
                    contact_msg = "Payments not yet configured — contact: Business@globalhealthcareaccess.com" if is_en else "Pagamentos em configuração — entre em contato: Business@globalhealthcareaccess.com"
                    st.warning(contact_msg)
                else:
                    base_url = "https://pharmaintel-br.onrender.com"
                    result   = create_checkout_session(
                        plan=plan_key,
                        period=selected_period,
                        email=email,
                        success_url=f"{base_url}/?session_id={{CHECKOUT_SESSION_ID}}",
                        cancel_url=f"{base_url}/",
                    )
                    if result.error:
                        err_label = "Checkout error:" if is_en else "Erro ao iniciar checkout:"
                        st.error(f"{err_label} {result.error}")
                    else:
                        st.markdown(
                            f'<meta http-equiv="refresh" content="0; url={result.url}">',
                            unsafe_allow_html=True,
                        )

    # Footer
    footer_line1 = "Payments securely processed via <b>Stripe</b> · Cancel anytime" if is_en else "Pagamentos processados com segurança via <b>Stripe</b> · Cancele a qualquer momento"
    footer_line2_label = "Questions?" if is_en else "Dúvidas?"
    st.markdown(f"""
    <div style="text-align:center; padding:2rem 0; color:#8899AA; font-size:0.8rem;">
      <p>{footer_line1}</p>
      <p>{footer_line2_label} <a href="mailto:Business@globalhealthcareaccess.com" style="color:#4DB6AC;">Business@globalhealthcareaccess.com</a></p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


def _handle_payment_success(session_id: str) -> None:
    """Verify Stripe session and create subscriber account after payment."""
    try:
        from src.payments.stripe_client import verify_checkout_session
        from src.db.database import init_db, get_user_by_email, create_user
        from src.db.models import User

        init_db()
        info = verify_checkout_session(session_id)

        if not info.ok:
            st.warning(f"Não foi possível verificar o pagamento: {info.error}")
            return

        # Create or update user account
        existing = get_user_by_email(info.email)
        if not existing:
            password = User.generate_password()
            create_user(
                email=info.email,
                password=password,
                plan=info.plan,
                period=info.period,
                stripe_customer_id=info.customer_id,
                stripe_subscription_id=info.subscription_id,
                subscription_status="active",
            )
            st.session_state["payment_processed"] = True
            st.success(f"""
            **Pagamento confirmado!** Bem-vindo ao PharmaIntel BR.

            **Seu email:** {info.email}
            **Sua senha:** `{password}`

            Guarde essa senha — ela não será exibida novamente.
            """)
        else:
            st.session_state["payment_processed"] = True
            st.info(f"Assinatura atualizada para o plano **{info.plan}**. Faça login com seu email e senha.")

    except Exception as exc:
        st.warning(f"Erro ao processar pagamento: {exc}")


def _page_landing() -> None:
    """Public landing page — bilingual PT/EN."""

    lang = st.session_state.get("lang", "PT")
    is_en = lang == "EN"

    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #0A1628; }
    [data-testid="stSidebar"] { display: none; }
    .hero-title { font-size: 3rem; font-weight: 800; color: #fff; line-height: 1.2; margin: 0; }
    .hero-accent { color: #4DB6AC; }
    .hero-sub { color: #8899AA; font-size: 1.15rem; margin: 1rem 0 2rem; line-height: 1.6; }
    .stat-box { background: #112240; border: 1px solid #1E3A5F; border-radius: 12px;
                padding: 1.5rem; text-align: center; }
    .stat-num { font-size: 2rem; font-weight: 700; color: #4DB6AC; }
    .stat-lbl { color: #8899AA; font-size: 0.85rem; margin-top: 0.25rem; }
    .feature-item { background: #112240; border: 1px solid #1E3A5F; border-radius: 12px;
                    padding: 1.25rem 1.5rem; margin-bottom: 0.75rem; }
    .feature-icon { font-size: 1.5rem; margin-right: 0.5rem; }
    .feature-title { color: #E2EAF4; font-weight: 600; font-size: 1rem; }
    .feature-desc { color: #8899AA; font-size: 0.85rem; margin-top: 0.25rem; }
    .source-badge { background: #0D2B45; border: 1px solid #1E3A5F; border-radius: 20px;
                    padding: 0.3rem 0.8rem; color: #4DB6AC; font-size: 0.8rem;
                    display: inline-block; margin: 0.2rem; }
    </style>
    """, unsafe_allow_html=True)

    # Top bar
    col_logo, col_nav = st.columns([3, 2])
    with col_logo:
        st.markdown('<span style="color:#4DB6AC; font-size:1.3rem; font-weight:700;">PharmaIntel AI</span>', unsafe_allow_html=True)
    with col_nav:
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("PT | EN", use_container_width=True, key="landing_lang"):
                st.session_state["lang"] = "EN" if lang == "PT" else "PT"
                st.rerun()
        with c2:
            if st.button("Sign In" if is_en else "Entrar", use_container_width=True):
                st.session_state["show_landing"] = False
                st.rerun()
        with c3:
            if st.button("See Plans" if is_en else "Ver Planos", use_container_width=True, type="primary"):
                st.session_state["show_pricing"] = True
                st.session_state["show_landing"] = False
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Hero
    if is_en:
        hero_html = """
        <div style="text-align:center; padding: 3rem 1rem 2rem;">
          <div class="hero-title">
            Pharmaceutical Intelligence<br>
            <span class="hero-accent">for the Brazilian Market</span>
          </div>
          <p class="hero-sub">
            Monitor imports, track ANVISA registrations and discover market opportunities<br>
            with real data and AI — all in one platform.
          </p>
        </div>"""
    else:
        hero_html = """
        <div style="text-align:center; padding: 3rem 1rem 2rem;">
          <div class="hero-title">
            Inteligência Farmacêutica<br>
            <span class="hero-accent">para o Mercado Brasileiro</span>
          </div>
          <p class="hero-sub">
            Monitore importações, rastreie registros ANVISA e descubra oportunidades<br>
            de mercado com dados reais e IA — tudo em uma plataforma.
          </p>
        </div>"""
    st.markdown(hero_html, unsafe_allow_html=True)

    # Stats
    s1, s2, s3, s4 = st.columns(4)
    stats = [
        ("US$ 12.35B", "Chapter 30 Imports · 2024" if is_en else "Importações Cap. 30 · 2024"),
        ("42.926",     "ANVISA Registrations"       if is_en else "Registros ANVISA"),
        ("817",        "Companies Mapped"            if is_en else "Empresas Mapeadas"),
        ("208",        "NCM/HS Codes Monitored"      if is_en else "NCMs Monitorados"),
    ]
    for col, (num, lbl) in zip([s1, s2, s3, s4], stats):
        col.markdown(f'<div class="stat-box"><div class="stat-num">{num}</div><div class="stat-lbl">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # Features + CTA
    f_col, cta_col = st.columns([3, 2])

    with f_col:
        st.markdown(f'<p style="color:#4DB6AC; font-weight:600; font-size:0.85rem; letter-spacing:1px;">{"FEATURES" if is_en else "FUNCIONALIDADES"}</p>', unsafe_allow_html=True)
        if is_en:
            features = [
                ("📊", "Import Dashboard",        "Real-time Comex Stat data by NCM/HS code, country and period"),
                ("🏛️", "ANVISA Monitoring",       "Active registrations, expiry alerts and compliance tracking"),
                ("🤖", "AI Agent",                "Strategic analysis with GPT-4o mini / Claude Sonnet — ask in English"),
                ("🌍", "Global Context",           "UN Comtrade data for international benchmarking"),
                ("🏢", "Company Intelligence",     "817 importers mapped with CNPJ and product portfolio"),
                ("🧬", "Patent Tracker",           "Expiry dates and biosimilar opportunities for key molecules"),
            ]
        else:
            features = [
                ("📊", "Dashboard de Importações", "Dados Comex Stat em tempo real por NCM, país e período"),
                ("🏛️", "Monitoramento ANVISA",     "Registros ativos, vencimentos e alertas de compliance"),
                ("🤖", "Agente IA",                "Análise estratégica com GPT-4o mini / Claude Sonnet"),
                ("🌍", "Contexto Global",           "Dados UN Comtrade para benchmarking internacional"),
                ("🏢", "Mapa de Empresas",          "817 importadores mapeados com CNPJ e portfólio"),
                ("🧬", "Patentes",                  "Vencimentos e oportunidades de biossimilares"),
            ]
        for icon, title, desc in features:
            st.markdown(f"""
            <div class="feature-item">
              <span class="feature-icon">{icon}</span>
              <span class="feature-title">{title}</span>
              <div class="feature-desc">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    with cta_col:
        if is_en:
            st.markdown('<p style="color:#4DB6AC; font-weight:600; font-size:0.85rem; letter-spacing:1px;">DATA INTEGRITY</p>', unsafe_allow_html=True)
            st.markdown("""
            <p style="color:#B0BEC5; font-size:0.85rem; line-height:1.6;">
              All data is sourced from <b style="color:#E2EAF4;">official government databases</b>,
              updated in real time. Our proprietary integration layer normalizes,
              validates and cross-references multiple sources so you always have
              accurate, audit-ready intelligence.
            </p>
            """, unsafe_allow_html=True)
        else:
            st.markdown('<p style="color:#4DB6AC; font-weight:600; font-size:0.85rem; letter-spacing:1px;">INTEGRIDADE DOS DADOS</p>', unsafe_allow_html=True)
            st.markdown("""
            <p style="color:#B0BEC5; font-size:0.85rem; line-height:1.6;">
              Todos os dados são provenientes de <b style="color:#E2EAF4;">bases governamentais oficiais</b>,
              atualizados em tempo real. Nossa camada de integração proprietária normaliza,
              valida e cruza múltiplas fontes para que você tenha sempre
              inteligência precisa e auditável.
            </p>
            """, unsafe_allow_html=True)

        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(f'<p style="color:#E2EAF4; font-weight:600; font-size:1rem;">{"Ready to start?" if is_en else "Pronto para começar?"}</p>', unsafe_allow_html=True)

        demo_cta = "Try the AI Free" if is_en else "Experimentar a IA Gratis"
        if st.button(demo_cta, use_container_width=True, type="primary"):
            st.session_state["show_demo_agent"] = True
            st.session_state["show_landing"]    = False
            st.session_state.pop("demo_question_used", None)
            st.session_state.pop("demo_question_text", None)
            st.session_state.pop("demo_answer_text",   None)
            st.rerun()
        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
        if st.button("See Plans & Pricing" if is_en else "Ver Planos e Preços", use_container_width=True):
            st.session_state["show_pricing"] = True
            st.session_state["show_landing"] = False
            st.rerun()
        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
        if st.button("I have an account — Sign In" if is_en else "Ja tenho conta — Entrar", use_container_width=True):
            st.session_state["show_landing"] = False
            st.rerun()

        st.markdown(f"""
        <p style="color:#8899AA; font-size:0.75rem; text-align:center; margin-top:1rem;">
          {"1 free question · No credit card · No sign-up" if is_en else "1 pergunta gratis · Sem cartão · Sem cadastro"}
        </p>
        """, unsafe_allow_html=True)

    # Footer
    st.markdown(f"""
    <hr style="border-color:#1E3A5F; margin:3rem 0 1rem;">
    <div style="text-align:center; color:#8899AA; font-size:0.8rem; padding-bottom:2rem;">
      © 2026 PharmaIntel AI · {"Brazilian public data" if is_en else "Dados públicos brasileiros"} ·
      <a href="mailto:Business@globalhealthcareaccess.com" style="color:#4DB6AC;">Business@globalhealthcareaccess.com</a>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


# Gate: show pricing page if requested (unauthenticated)
if not st.session_state.get("authenticated", False):
    if st.session_state.get("show_demo_agent", False):
        _page_demo_agent()
    elif st.session_state.get("show_trial_success", False):
        _page_trial_success()
    elif st.session_state.get("show_trial_register", False):
        _page_trial_register()
    elif st.session_state.get("show_pricing", False):
        _page_pricing()
    elif st.session_state.get("show_landing", True):
        _page_landing()
    else:
        _login_page()

# ---------------------------------------------------------------------------
# Theme — Dark Teal
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ─── Base ─────────────────────────────────────────────────────────────── */
:root {
    --teal:       #00897B;
    --teal-light: #4DB6AC;
    --teal-dark:  #00574B;
    --cyan:       #26C6DA;
    --bg:         #0A1628;
    --bg-card:    #112240;
    --bg-sidebar: #0D1B2E;
    --border:     #1E3A5F;
    --text:       #E2EAF4;
    --text-muted: #8899AA;
}

html, body, [data-testid="stAppViewContainer"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}

[data-testid="stSidebar"] {
    background-color: var(--bg-sidebar) !important;
    border-right: 1px solid var(--border);
}

/* ─── Header ────────────────────────────────────────────────────────────── */
.ph-header {
    background: linear-gradient(135deg, var(--teal-dark) 0%, #0D2B45 60%, var(--bg) 100%);
    border-bottom: 2px solid var(--teal);
    padding: 1.5rem 2rem;
    margin: -1rem -1rem 1.5rem -1rem;
    border-radius: 0 0 12px 12px;
}
.ph-header h1 {
    color: #fff;
    font-size: 1.8rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.5px;
}
.ph-header p {
    color: var(--teal-light);
    margin: 0.25rem 0 0;
    font-size: 0.9rem;
}

/* ─── KPI Cards ─────────────────────────────────────────────────────────── */
.kpi-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-top: 3px solid var(--teal);
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 0.5rem;
    transition: border-color 0.2s;
}
.kpi-card:hover { border-top-color: var(--cyan); }
.kpi-label {
    color: var(--text-muted);
    font-size: 0.78rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 0.4rem;
}
.kpi-value {
    color: #fff;
    font-size: 1.6rem;
    font-weight: 700;
    line-height: 1.1;
}
.kpi-sub {
    color: var(--teal-light);
    font-size: 0.8rem;
    margin-top: 0.3rem;
}

/* ─── Section titles ─────────────────────────────────────────────────────── */
.section-title {
    color: var(--teal-light);
    font-size: 1rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.5rem;
    margin-bottom: 1rem;
}

/* ─── Status badges ──────────────────────────────────────────────────────── */
.badge-ok   { background:#00574B; color:#4DB6AC; padding:2px 8px; border-radius:4px; font-size:0.75rem; }
.badge-warn { background:#4A3000; color:#FFB300; padding:2px 8px; border-radius:4px; font-size:0.75rem; }
.badge-err  { background:#4A0000; color:#FF5252; padding:2px 8px; border-radius:4px; font-size:0.75rem; }

/* ─── Chat ───────────────────────────────────────────────────────────────── */
.chat-user { background:#1A2E4A; border-radius:10px 10px 2px 10px; padding:0.75rem 1rem; margin:0.5rem 0; }
.chat-ai   { background:var(--bg-card); border-left:3px solid var(--teal); border-radius:2px 10px 10px 10px; padding:0.75rem 1rem; margin:0.5rem 0; }

/* ─── Streamlit overrides ────────────────────────────────────────────────── */
[data-testid="metric-container"] { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem; }
.stButton>button { background: var(--teal); color: #fff; border: none; border-radius: 6px; font-weight: 600; }
.stButton>button:hover { background: var(--teal-light); }
div[data-testid="stSelectbox"] label, div[data-testid="stSlider"] label { color: var(--text-muted) !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Plotly theme (dark teal)
# ---------------------------------------------------------------------------
PLOTLY_LAYOUT = dict(
    paper_bgcolor="#0A1628",
    plot_bgcolor="#112240",
    font=dict(color="#E2EAF4", family="Inter, Segoe UI, system-ui"),
    xaxis=dict(gridcolor="#1E3A5F", zerolinecolor="#1E3A5F"),
    yaxis=dict(gridcolor="#1E3A5F", zerolinecolor="#1E3A5F"),
    margin=dict(l=50, r=20, t=50, b=50),
    colorway=["#00897B","#26C6DA","#4DB6AC","#80CBC4","#00BFA5",
              "#006064","#0097A7","#00838F","#4DD0E1","#80DEEA"],
)

TEAL_SEQ = ["#0D1B2E","#00574B","#00897B","#4DB6AC","#B2DFDB","#E0F2F1"]

COLOR_PRIMARY = "#00897B"
COLOR_ACCENT  = "#26C6DA"


def apply_theme(fig: go.Figure, title: str = "") -> go.Figure:
    """Apply dark teal theme to a Plotly figure. Avoids Plotly 6.x legend duplicate bug."""
    update_kwargs = dict(**PLOTLY_LAYOUT)
    if title:
        update_kwargs["title"] = dict(text=title, font=dict(size=15, color="#E2EAF4"))
    # Single 'legend' dict — do NOT pass both legend=dict() and legend_* kwargs
    update_kwargs["legend"] = dict(
        bgcolor="rgba(0,0,0,0)",
        bordercolor="#1E3A5F",
        font=dict(color="#8899AA", size=11),
    )
    fig.update_layout(**update_kwargs)
    return fig


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def load_parquet(name: str, year: int) -> pd.DataFrame:
    path = PROCESSED_DIR / f"{name}_{year}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame()


def demo_imports(year: int = 2024, n: int = 500) -> pd.DataFrame:
    """Generate realistic demo import data when real data is unavailable."""
    rng = np.random.default_rng(42)
    ncms = [
        ("30049099", "Outros medicamentos"), ("30049019", "Antibióticos"),
        ("30043900", "Hormônios"), ("30059010", "Curativos"),
        ("30021590", "Vacinas"), ("30064000", "Cimentos dentários"),
        ("30061000", "Suturas estéreis"), ("30049031", "Insulina"),
        ("30045000", "Vitaminas"), ("30049059", "Anestésicos"),
        ("30049079", "Antivirais"), ("30049089", "Antineoplásicos"),
    ]
    countries = ["Germany","United States","India","China","Italy","Switzerland","France","Ireland","Belgium","Spain"]
    months = rng.integers(1, 13, n)
    ncm_idx = rng.integers(0, len(ncms), n)
    rows = []
    for i in range(n):
        co_ncm, ds_ncm = ncms[ncm_idx[i]]
        fob = float(rng.lognormal(13, 1.8))
        kg = fob / rng.uniform(15, 80)
        rows.append({
            "co_ano": year, "co_mes": int(months[i]),
            "co_ncm": co_ncm, "ds_ncm": ds_ncm,
            "ds_pais": countries[rng.integers(0, len(countries))],
            "vl_fob": fob, "kg_liquido": kg,
            "vl_fob_brl": fob * 5.10,
            "preco_usd_kg": fob / kg,
            "risco_regulatorio": float(rng.uniform(0, 8)),
            "anvisa_ativo": bool(rng.random() > 0.15),
        })
    df = pd.DataFrame(rows)
    df["periodo"] = pd.to_datetime(dict(year=df["co_ano"], month=df["co_mes"], day=1))
    return df


def demo_comtrade(year: int = 2024) -> pd.DataFrame:
    rng = np.random.default_rng(99)
    partners = [
        ("Germany", 680e6), ("United States", 520e6), ("India", 410e6),
        ("China", 380e6), ("Italy", 290e6), ("Switzerland", 260e6),
        ("Netherlands", 190e6), ("France", 170e6), ("Spain", 140e6),
        ("United Kingdom", 120e6),
    ]
    rows = []
    for country, base in partners:
        rows.append({
            "partner": country,
            "vl_usd": float(base * rng.uniform(0.85, 1.15)),
            "kg_liquido": float(base / rng.uniform(40, 90)),
            "ano": year,
            "_demo": True,
        })
    df = pd.DataFrame(rows).sort_values("vl_usd", ascending=False)
    df["participacao_pct"] = (df["vl_usd"] / df["vl_usd"].sum() * 100).round(2)
    return df


def load_or_demo_imports(year: int) -> tuple[pd.DataFrame, bool]:
    df = load_parquet("pharma_imports", year)
    if df.empty:
        return demo_imports(year), True
    return df, False


def load_or_demo_comtrade(year: int) -> tuple[pd.DataFrame, bool]:
    df = load_parquet("comtrade", year)
    if df.empty:
        return demo_comtrade(year), True
    return df, False


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
def render_header(page: str) -> None:
    st.markdown(f"""
    <div class="ph-header">
      <h1>💊 PharmaIntel BR</h1>
      <p>{_t("subtitle")} &nbsp;·&nbsp; {page}</p>
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# KPI card helper
# ---------------------------------------------------------------------------
def kpi_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      {sub_html}
    </div>
    """


def fmt_usd(v: float) -> str:
    if v >= 1e9:
        return f"US$ {v/1e9:.2f}B"
    if v >= 1e6:
        return f"US$ {v/1e6:.1f}M"
    return f"US$ {v:,.0f}"


def fmt_brl(v: float) -> str:
    if v >= 1e9:
        return f"R$ {v/1e9:.2f}B"
    if v >= 1e6:
        return f"R$ {v/1e6:.1f}M"
    return f"R$ {v:,.0f}"


# ---------------------------------------------------------------------------
# Demo warning banner
# ---------------------------------------------------------------------------
def demo_warning() -> None:
    st.info(_t("demo_msg"), icon="ℹ️")


# ===========================================================================
# Pages
# ===========================================================================

def page_overview(year: int) -> None:
    render_header(_t("header_overview"))

    df, is_demo = load_or_demo_imports(year)
    if is_demo:
        demo_warning()

    # ── KPIs ────────────────────────────────────────────────────────────────
    total_fob = df["vl_fob"].sum() if "vl_fob" in df.columns else 0
    total_kg  = df["kg_liquido"].sum() if "kg_liquido" in df.columns else 0
    n_ops     = len(df)
    n_ncms    = df["co_ncm"].nunique() if "co_ncm" in df.columns else 0
    n_paises  = df["ds_pais"].nunique() if "ds_pais" in df.columns else 0

    cols = st.columns(5)
    kpis = [
        (_t("kpi_total_fob"),     fmt_usd(total_fob),          f"{_t('kpi_chapter')} · {year}"),
        (_t("kpi_total_fob_brl"), fmt_brl(total_fob * 5.10),   "USD × R$5,10"),
        (_t("kpi_volume"),        f"{total_kg/1e6:.1f}M kg",   _t("kpi_net_weight")),
        (_t("kpi_ncms"),          f"{n_ncms}",                  _t("kpi_chapter")),
        (_t("kpi_countries"),     f"{n_paises}",                _t("kpi_active_suppliers")),
    ]
    for col, (label, value, sub) in zip(cols, kpis):
        col.markdown(kpi_card(label, value, sub), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts row 1 ────────────────────────────────────────────────────────
    c1, c2 = st.columns([3, 2])

    with c1:
        st.markdown(f'<div class="section-title">{_t("chart_monthly")}</div>', unsafe_allow_html=True)
        if "co_mes" in df.columns and "vl_fob" in df.columns:
            monthly = (
                df.groupby("co_mes")
                .agg(fob=("vl_fob", "sum"), ops=("vl_fob", "count"))
                .reset_index()
                .sort_values("co_mes")
            )
            MONTHS = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
            monthly["mes_nome"] = monthly["co_mes"].apply(lambda m: MONTHS[int(m)-1] if 1 <= int(m) <= 12 else str(m))

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=monthly["mes_nome"], y=monthly["fob"] / 1e6,
                name="FOB (USD M)", marker_color=COLOR_PRIMARY, opacity=0.85,
            ))
            fig.add_trace(go.Scatter(
                x=monthly["mes_nome"], y=monthly["fob"] / 1e6,
                mode="lines+markers", name=_t("chart_trend"),
                line=dict(color=COLOR_ACCENT, width=2),
                marker=dict(size=6, color=COLOR_ACCENT),
            ))
            apply_theme(fig, f"Importações Mensais {year} (US$ Milhões)")
            fig.update_yaxes(title_text="USD Milhões")
            st.plotly_chart(fig, width="stretch")

    with c2:
        st.markdown(f'<div class="section-title">{_t("chart_top_countries")}</div>', unsafe_allow_html=True)
        if "ds_pais" in df.columns and "vl_fob" in df.columns:
            top_paises = (
                df.groupby("ds_pais")["vl_fob"].sum()
                .sort_values(ascending=False)
                .head(8)
                .reset_index()
            )
            top_paises.columns = ["Pais", "fob"]
            fig2 = px.bar(
                top_paises, x="fob", y="Pais", orientation="h",
                color="fob", color_continuous_scale=TEAL_SEQ,
            )
            apply_theme(fig2, "Por Valor FOB (USD)")
            fig2.update_xaxes(title_text="USD")
            fig2.update_coloraxes(showscale=False)
            st.plotly_chart(fig2, width="stretch")

    # ── Charts row 2 ────────────────────────────────────────────────────────
    c3, c4 = st.columns(2)

    with c3:
        st.markdown('<div class="section-title">Top 10 NCMs por FOB</div>', unsafe_allow_html=True)
        if "co_ncm" in df.columns and "vl_fob" in df.columns:
            top_ncm = (
                df.groupby("co_ncm")["vl_fob"].sum()
                .sort_values(ascending=False)
                .head(10)
                .reset_index()
            )
            top_ncm.columns = ["NCM", "fob"]
            fig3 = px.bar(
                top_ncm, x="NCM", y="fob",
                color="fob", color_continuous_scale=TEAL_SEQ,
            )
            apply_theme(fig3, "Ranking NCMs — Valor FOB")
            fig3.update_coloraxes(showscale=False)
            fig3.update_xaxes(tickangle=-45)
            st.plotly_chart(fig3, width="stretch")

    with c4:
        st.markdown('<div class="section-title">Distribuição de Risco Regulatório</div>', unsafe_allow_html=True)
        if "risco_regulatorio" in df.columns:
            bins = [0, 2, 4, 6, 8, 10]
            labels = ["Muito Baixo (0-2)", "Baixo (2-4)", "Médio (4-6)", "Alto (6-8)", "Crítico (8-10)"]
            df["faixa_risco"] = pd.cut(df["risco_regulatorio"], bins=bins, labels=labels, right=True)
            risk_dist = df["faixa_risco"].value_counts().reset_index()
            risk_dist.columns = ["Faixa", "count"]
            colors_risk = ["#00897B","#4DB6AC","#FFB300","#FF6D00","#FF1744"]
            fig4 = px.pie(
                risk_dist, names="Faixa", values="count",
                color_discrete_sequence=colors_risk,
                hole=0.45,
            )
            apply_theme(fig4, "Operações por Faixa de Risco")
            st.plotly_chart(fig4, width="stretch")


def page_importacoes(year: int) -> None:
    render_header(_t("header_imports"))

    df, is_demo = load_or_demo_imports(year)
    if is_demo:
        demo_warning()

    # Filters
    with st.expander("Filtros", expanded=True):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            ncm_options = ["Todos"] + sorted(df["co_ncm"].unique().tolist()) if "co_ncm" in df.columns else ["Todos"]
            ncm_sel = st.selectbox("Código NCM", ncm_options)
        with fc2:
            pais_options = ["Todos"] + sorted(df["ds_pais"].dropna().unique().tolist()) if "ds_pais" in df.columns else ["Todos"]
            pais_sel = st.selectbox("País de Origem", pais_options)
        with fc3:
            if "risco_regulatorio" in df.columns:
                min_r, max_r = float(df["risco_regulatorio"].min()), float(df["risco_regulatorio"].max())
                risco_range = st.slider("Risco Regulatório", min_r, max_r, (min_r, max_r), step=0.5)
            else:
                risco_range = (0.0, 10.0)

    mask = pd.Series(True, index=df.index)
    if ncm_sel != "Todos" and "co_ncm" in df.columns:
        mask &= df["co_ncm"] == ncm_sel
    if pais_sel != "Todos" and "ds_pais" in df.columns:
        mask &= df["ds_pais"] == pais_sel
    if "risco_regulatorio" in df.columns:
        mask &= df["risco_regulatorio"].between(risco_range[0], risco_range[1])
    df_f = df[mask].copy()

    st.caption(f"{len(df_f):,} operações filtradas")

    # ── Scatter: FOB vs Preço/kg ─────────────────────────────────────────────
    if "preco_usd_kg" in df_f.columns and "vl_fob" in df_f.columns:
        st.markdown('<div class="section-title">FOB vs. Preço Unitário (USD/kg)</div>', unsafe_allow_html=True)
        plot_df = df_f.dropna(subset=["preco_usd_kg", "vl_fob"]).copy()
        plot_df = plot_df[plot_df["preco_usd_kg"] < plot_df["preco_usd_kg"].quantile(0.99)]
        color_col = "risco_regulatorio" if "risco_regulatorio" in plot_df.columns else None
        hover = ["co_ncm"] + (["ds_ncm"] if "ds_ncm" in plot_df.columns else []) + (["ds_pais"] if "ds_pais" in plot_df.columns else [])

        fig = px.scatter(
            plot_df.sample(min(len(plot_df), 400), random_state=42),
            x="preco_usd_kg", y="vl_fob",
            color=color_col,
            color_continuous_scale=["#00897B","#FFB300","#FF1744"],
            hover_data=hover,
            size_max=15,
            opacity=0.7,
        )
        apply_theme(fig, "FOB × Preço/kg — Cada ponto = 1 operação")
        fig.update_xaxes(title_text="Preço (USD/kg)")
        fig.update_yaxes(title_text="Valor FOB (USD)")
        fig.update_coloraxes(colorbar=dict(title="Risco"))
        st.plotly_chart(fig, width="stretch")

    # ── Table ───────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Dados Detalhados</div>', unsafe_allow_html=True)
    show_cols = [c for c in ["co_ncm","ds_ncm","ds_pais","co_mes","vl_fob","kg_liquido","preco_usd_kg","risco_regulatorio"] if c in df_f.columns]
    display = df_f[show_cols].copy()
    rename_map = {
        "co_ncm": "NCM", "ds_ncm": "Descrição", "ds_pais": "País",
        "co_mes": "Mês", "vl_fob": "FOB (USD)", "kg_liquido": "Volume (kg)",
        "preco_usd_kg": "Preço USD/kg", "risco_regulatorio": "Risco",
    }
    display = display.rename(columns={k: v for k, v in rename_map.items() if k in display.columns})
    for col in ["FOB (USD)", "Volume (kg)", "Preço USD/kg"]:
        if col in display.columns:
            display[col] = display[col].round(2)

    st.dataframe(
        display.head(200),
        width="stretch",
        hide_index=True,
        column_config={
            "FOB (USD)": st.column_config.NumberColumn(format="$ %.2f"),
            "Risco": st.column_config.ProgressColumn(min_value=0, max_value=10, format="%.1f"),
        },
    )

    if not df_f.empty:
        csv = df_f.to_csv(index=False).encode("utf-8")
        st.download_button("Exportar CSV", csv, f"pharmaintel_importacoes_{year}.csv", "text/csv")


def page_anvisa(year: int) -> None:
    render_header(_t("header_anvisa"))

    df, is_demo = load_or_demo_imports(year)
    if is_demo:
        demo_warning()

    # Compliance summary
    if "anvisa_ativo" in df.columns:
        n_total  = len(df)
        n_ativo  = df["anvisa_ativo"].sum()
        n_risco  = n_total - n_ativo
        pct_ok   = n_ativo / n_total * 100 if n_total else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(kpi_card("Total Operações", f"{n_total:,}", ""), unsafe_allow_html=True)
        c2.markdown(kpi_card("Com Registro ANVISA", f"{n_ativo:,}", f"{pct_ok:.1f}%"), unsafe_allow_html=True)
        c3.markdown(kpi_card("Em Risco", f"{n_risco:,}", "Sem registro ativo"), unsafe_allow_html=True)
        c4.markdown(kpi_card("Conformidade", f"{pct_ok:.0f}%", "meta: 100%"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Risco por NCM
        if "co_ncm" in df.columns and "risco_regulatorio" in df.columns:
            st.markdown('<div class="section-title">Risco Regulatório por NCM (Top 15)</div>', unsafe_allow_html=True)
            risk_ncm = (
                df.groupby("co_ncm")
                .agg(
                    risco_medio=("risco_regulatorio", "mean"),
                    fob_total=("vl_fob", "sum"),
                    operacoes=("vl_fob", "count"),
                )
                .reset_index()
                .sort_values("risco_medio", ascending=False)
                .head(15)
            )
            fig = px.bar(
                risk_ncm, x="co_ncm", y="risco_medio",
                color="risco_medio",
                color_continuous_scale=["#00897B","#FFB300","#FF1744"],
                text="risco_medio",
            )
            apply_theme(fig, "Risco Regulatório Médio por NCM")
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            fig.update_xaxes(title_text="NCM", tickangle=-45)
            fig.update_yaxes(title_text="Risco (0–10)", range=[0, 11])
            fig.update_coloraxes(colorbar=dict(title="Risco"))
            st.plotly_chart(fig, width="stretch")
    else:
        st.info("Dados de compliance ANVISA não disponíveis. Execute o ETL para integrar os registros.", icon="ℹ️")


def page_comtrade(year: int) -> None:
    render_header(_t("header_comtrade"))

    df, is_demo = load_or_demo_comtrade(year)
    if is_demo:
        demo_warning()

    if df.empty:
        st.warning("Dados Comtrade não disponíveis.")
        return

    total_usd = df["vl_usd"].sum() if "vl_usd" in df.columns else 0
    n_partners = df["partner"].nunique() if "partner" in df.columns else 0

    c1, c2 = st.columns(2)
    c1.markdown(kpi_card("Total Importado (Global)", fmt_usd(total_usd), f"UN Comtrade · Brasil · {year}"), unsafe_allow_html=True)
    c2.markdown(kpi_card("Parceiros Comerciais", f"{n_partners}", "Países fornecedores"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown('<div class="section-title">Importações por País (USD)</div>', unsafe_allow_html=True)
        if "partner" in df.columns and "vl_usd" in df.columns:
            fig = px.bar(
                df.sort_values("vl_usd", ascending=True).tail(15),
                x="vl_usd", y="partner", orientation="h",
                color="vl_usd", color_continuous_scale=TEAL_SEQ,
            )
            apply_theme(fig, f"Brasil — Importações Farmacêuticas {year}")
            fig.update_xaxes(title_text="USD")
            fig.update_yaxes(title_text="")
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, width="stretch")

    with c2:
        st.markdown('<div class="section-title">Share de Mercado por País (%)</div>', unsafe_allow_html=True)
        if "partner" in df.columns and "participacao_pct" in df.columns:
            fig2 = px.pie(
                df.head(10), names="partner", values="participacao_pct",
                color_discrete_sequence=PLOTLY_LAYOUT["colorway"],
                hole=0.4,
            )
            apply_theme(fig2)
            st.plotly_chart(fig2, width="stretch")

    # Preço médio FOB/kg
    if "vl_usd" in df.columns and "kg_liquido" in df.columns:
        st.markdown('<div class="section-title">Preço Médio (USD/kg) por País</div>', unsafe_allow_html=True)
        df2 = df.copy()
        df2["preco_usd_kg"] = np.where(df2["kg_liquido"] > 0, df2["vl_usd"] / df2["kg_liquido"], np.nan)
        df2 = df2.dropna(subset=["preco_usd_kg"]).sort_values("preco_usd_kg", ascending=False)
        fig3 = px.bar(
            df2, x="partner", y="preco_usd_kg",
            color="preco_usd_kg", color_continuous_scale=TEAL_SEQ,
        )
        apply_theme(fig3, "Preço FOB Médio por País Fornecedor")
        fig3.update_yaxes(title_text="USD/kg")
        fig3.update_xaxes(title_text="País", tickangle=-45)
        fig3.update_coloraxes(showscale=False)
        st.plotly_chart(fig3, width="stretch")


def page_empresas(year: int) -> None:
    render_header(_t("header_companies"))

    PROCESSED_DIR_LOCAL = ROOT / "data" / "processed"
    emp_path  = PROCESSED_DIR_LOCAL / "empresas_anvisa.parquet"
    link_path = PROCESSED_DIR_LOCAL / "ncm_empresa_link.parquet"

    if not emp_path.exists():
        st.warning(
            "Dados de empresas não encontrados. Execute o **Pipeline ETL** para extrair "
            "as empresas dos 42.926 registros ANVISA.",
            icon="⚠️",
        )
        if st.button("Extrair Empresas Agora", type="primary"):
            with st.spinner("Extraindo dados de empresas da ANVISA..."):
                try:
                    from src.integrations.anvisa import fetch_medicamentos_registrados
                    from src.integrations.anvisa_empresas import load_or_build
                    anvisa_df = fetch_medicamentos_registrados(use_cache=True)
                    emp_df, link_df = load_or_build(anvisa_df, force=True)
                    st.success(f"Extraídas {len(emp_df)} empresas e {len(link_df)} links NCM-empresa.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro: {exc}")
        return

    @st.cache_data(ttl=300)
    def _load_emp():
        return pd.read_parquet(emp_path)

    @st.cache_data(ttl=300)
    def _load_link():
        return pd.read_parquet(link_path)

    emp_df  = _load_emp()
    link_df = _load_link()

    # ── KPIs ────────────────────────────────────────────────────────────────
    n_total    = len(emp_df)
    n_ativos   = int((emp_df["registros_ativos"] > 0).sum()) if "registros_ativos" in emp_df.columns else 0
    n_alertas  = int((emp_df["alertas_vencendo"] > 0).sum()) if "alertas_vencendo"  in emp_df.columns else 0
    n_vencidos = int((emp_df["registros_vencidos"] > 0).sum()) if "registros_vencidos" in emp_df.columns else 0
    media_conf = emp_df["pct_conformidade"].mean() if "pct_conformidade" in emp_df.columns else 0

    cols = st.columns(5)
    cols[0].markdown(kpi_card("Empresas Cadastradas", f"{n_total:,}", "ANVISA aberto"), unsafe_allow_html=True)
    cols[1].markdown(kpi_card("Com Registros Ativos", f"{n_ativos:,}", f"{n_ativos/n_total*100:.0f}% do total"), unsafe_allow_html=True)
    cols[2].markdown(kpi_card("Conformidade Média", f"{media_conf:.1f}%", "% registros ativos"), unsafe_allow_html=True)
    cols[3].markdown(kpi_card("Alertas — Vencendo", f"{n_alertas:,}", "próximos 6 meses"), unsafe_allow_html=True)
    cols[4].markdown(kpi_card("Com Reg. Vencidos",  f"{n_vencidos:,}", "requer renovação"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs ────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["Top Importadores", "Compliance", "NCM × Empresa", "Busca"])

    # ── Tab 1: Top companies by active registrations ─────────────────────
    with tab1:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown('<div class="section-title">Top 20 Empresas — Registros Ativos</div>', unsafe_allow_html=True)
            top20 = emp_df.head(20).copy()
            if not top20.empty:
                fig = px.bar(
                    top20,
                    x="registros_ativos",
                    y="razao_social",
                    orientation="h",
                    color="pct_conformidade",
                    color_continuous_scale=["#FF1744", "#FFB300", "#00897B"],
                    range_color=[0, 100],
                    hover_data=["cnpj_fmt", "total_registros", "alertas_vencendo"],
                )
                apply_theme(fig, "Registros ANVISA Ativos por Empresa")
                fig.update_yaxes(title_text="", tickfont=dict(size=10))
                fig.update_xaxes(title_text="Registros Ativos")
                fig.update_coloraxes(colorbar=dict(title="Conformidade (%)"))
                fig.update_layout(height=600)
                st.plotly_chart(fig, width="stretch")

        with c2:
            st.markdown('<div class="section-title">Distribuição por Categoria</div>', unsafe_allow_html=True)
            if "pct_conformidade" in emp_df.columns:
                bins = [0, 25, 50, 75, 90, 100]
                labels = ["0-25%", "25-50%", "50-75%", "75-90%", "90-100%"]
                emp_df["faixa_conf"] = pd.cut(emp_df["pct_conformidade"], bins=bins, labels=labels)
                dist = emp_df["faixa_conf"].value_counts().sort_index().reset_index()
                dist.columns = ["Faixa", "count"]
                colors = ["#FF1744", "#FF6D00", "#FFB300", "#4DB6AC", "#00897B"]
                fig2 = px.bar(dist, x="Faixa", y="count", color="Faixa",
                              color_discrete_sequence=colors)
                apply_theme(fig2, "Empresas por Faixa de Conformidade")
                fig2.update_layout(showlegend=False)
                fig2.update_xaxes(title_text="Conformidade")
                fig2.update_yaxes(title_text="Nº Empresas")
                st.plotly_chart(fig2, width="stretch")

    # ── Tab 2: Compliance alerts ─────────────────────────────────────────
    with tab2:
        st.markdown('<div class="section-title">Alertas de Vencimento de Registro</div>', unsafe_allow_html=True)
        st.caption("Empresas com registros vencendo nos próximos 6 meses ou já vencidos — risco de interrupção de importação.")

        alertas_df = emp_df[
            (emp_df.get("alertas_vencendo", pd.Series(0, index=emp_df.index)) > 0) |
            (emp_df.get("registros_vencidos", pd.Series(0, index=emp_df.index)) > 0)
        ].copy().sort_values("alertas_vencendo", ascending=False)

        if alertas_df.empty:
            st.success("Nenhum alerta de vencimento identificado.")
        else:
            st.caption(f"{len(alertas_df)} empresas em situação de alerta")

            show_cols = [c for c in ["razao_social","cnpj_fmt","registros_ativos",
                                      "alertas_vencendo","registros_vencidos","pct_conformidade"] if c in alertas_df.columns]
            display = alertas_df[show_cols].rename(columns={
                "razao_social": "Empresa", "cnpj_fmt": "CNPJ",
                "registros_ativos": "Reg. Ativos", "alertas_vencendo": "Vencendo (6m)",
                "registros_vencidos": "Já Vencidos", "pct_conformidade": "Conformidade (%)",
            })
            st.dataframe(
                display.head(50),
                width="stretch",
                hide_index=True,
                column_config={
                    "Conformidade (%)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                    "Vencendo (6m)": st.column_config.NumberColumn(help="Registros vencendo nos próximos 6 meses"),
                    "Já Vencidos": st.column_config.NumberColumn(help="Registros já vencidos — requer renovação urgente"),
                },
            )

    # ── Tab 3: NCM × Empresa linkage ─────────────────────────────────────
    with tab3:
        st.markdown('<div class="section-title">Empresas por NCM (via Classe Terapêutica ANVISA)</div>', unsafe_allow_html=True)
        st.info(
            "Linkage estimado: cruzamos as classes terapêuticas dos produtos registrados de cada empresa "
            "com o mapeamento NCM → categoria de produto. **Não é dado de importação real por CNPJ** — "
            "o Comex Stat público não divulga importador por operação.",
            icon="ℹ️",
        )

        if not link_df.empty:
            # Top NCMs by company count
            ncm_counts = (
                link_df.groupby("co_ncm")
                .agg(n_empresas=("cnpj", "nunique"), total_reg_ativos=("registros_ativos", "sum"))
                .reset_index()
                .sort_values("n_empresas", ascending=False)
                .head(20)
            )

            # Merge NCM descriptions from imports
            imports = load_parquet("pharma_imports", year)
            if not imports.empty and "ds_ncm" in imports.columns:
                desc = imports[["co_ncm","ds_ncm"]].drop_duplicates("co_ncm")
                ncm_counts = ncm_counts.merge(desc, on="co_ncm", how="left")
                ncm_counts["label"] = ncm_counts["co_ncm"] + " — " + ncm_counts["ds_ncm"].fillna("").str[:40]
            else:
                ncm_counts["label"] = ncm_counts["co_ncm"]

            c1, c2 = st.columns([2, 3])
            with c1:
                fig3 = px.bar(
                    ncm_counts, x="n_empresas", y="co_ncm", orientation="h",
                    color="n_empresas", color_continuous_scale=TEAL_SEQ,
                    hover_data=["label"],
                )
                apply_theme(fig3, "Empresas Mapeadas por NCM")
                fig3.update_yaxes(title_text="NCM")
                fig3.update_xaxes(title_text="Nº Empresas")
                fig3.update_coloraxes(showscale=False)
                st.plotly_chart(fig3, width="stretch")

            with c2:
                ncm_sel = st.selectbox("Selecione um NCM para ver as empresas:", ncm_counts["co_ncm"].tolist())
                if ncm_sel:
                    sub = link_df[link_df["co_ncm"] == ncm_sel].sort_values("registros_ativos", ascending=False)
                    show = sub[["razao_social","cnpj_fmt","registros_ativos","pct_conformidade","alertas_vencendo"]].rename(columns={
                        "razao_social": "Empresa", "cnpj_fmt": "CNPJ",
                        "registros_ativos": "Reg. Ativos", "pct_conformidade": "Conformidade (%)",
                        "alertas_vencendo": "Alertas",
                    })
                    st.dataframe(
                        show,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Conformidade (%)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                        },
                    )

    # ── Tab 4: Company search ──────────────────────────────────────────────
    with tab4:
        st.markdown('<div class="section-title">Buscar Empresa</div>', unsafe_allow_html=True)
        query = st.text_input("Nome ou parte do nome da empresa (mín. 3 caracteres):", placeholder="Ex: SANOFI, PFIZER, EMS...")

        if query and len(query) >= 3:
            mask = emp_df["razao_social"].str.upper().str.contains(query.upper(), na=False)
            results = emp_df[mask].copy()

            if results.empty:
                st.warning(f"Nenhuma empresa encontrada para '{query}'.")
            else:
                st.caption(f"{len(results)} empresa(s) encontrada(s)")
                for _, row in results.head(5).iterrows():
                    with st.expander(f"**{row['razao_social']}** — CNPJ: {row.get('cnpj_fmt', 'N/D')}"):
                        mc1, mc2, mc3 = st.columns(3)
                        mc1.metric("Registros Ativos",   int(row.get("registros_ativos", 0)))
                        mc2.metric("Conformidade",        f"{row.get('pct_conformidade', 0):.1f}%")
                        mc3.metric("Alertas Vencimento",  int(row.get("alertas_vencendo", 0)))

                        ncms = _safe_list(row.get("ncms_estimados"))
                        if len(ncms) > 0:
                            st.markdown(f"**NCMs estimados:** `{'`, `'.join(ncms)}`")
                            st.caption("Baseado em correspondência de classe terapêutica ANVISA × NCM")

                        classes = _safe_list(row.get("principais_classes"))
                        if len(classes) > 0:
                            st.markdown("**Principais classes terapêuticas:**")
                            for cl in classes:
                                st.markdown(f"  - {cl}")


def page_etl(year: int) -> None:
    render_header(_t("header_etl"))

    st.markdown("""
    O pipeline ETL do PharmaIntel BR processa dados de três fontes:

    | # | Estágio | Descrição |
    |---|---------|-----------|
    | 1 | **EXTRACT** | Coleta dados de Comex Stat, ANVISA e UN Comtrade |
    | 2 | **VALIDATE** | Verifica qualidade, completude e tipos |
    | 3 | **TRANSFORM** | Normaliza encoding, datas, moeda e cria métricas derivadas |
    | 4 | **ENRICH** | Join de fontes + score de risco regulatório |
    | 5 | **LOAD** | Persiste Parquet em `data/processed/` |
    """)

    st.markdown('<div class="section-title">Executar Pipeline</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        run_year = st.selectbox("Ano", [2026, 2025, 2024, 2023, 2022], index=1)
    with col2:
        force = st.checkbox("Forçar re-download", value=False)
    with col3:
        usd_brl = st.slider("Câmbio USD/BRL", 4.5, 6.5, 5.10, step=0.05)

    if st.button("Executar ETL", type="primary"):
        with st.spinner("Executando pipeline ETL..."):
            try:
                from src.utils.etl_pipeline import PharmaETLPipeline

                progress = st.progress(0)
                status   = st.empty()

                stages = ["EXTRACT", "VALIDATE", "TRANSFORM", "ENRICH", "LOAD"]
                pipeline = PharmaETLPipeline(year=run_year, usd_brl=usd_brl, force_refresh=force)
                result = pipeline.run()

                for i, stage in enumerate(stages):
                    progress.progress((i + 1) / len(stages))
                    ok = stage in result.stages_completed
                    status.markdown(f"{'✅' if ok else '❌'} {stage}")

                if result.success:
                    st.success(f"ETL concluído com sucesso! {result.rows_processed:,} linhas processadas em {result.duration_sec:.1f}s.")
                    st.cache_data.clear()
                else:
                    st.error(f"ETL falhou nos estágios: {result.errors}")

            except Exception as exc:
                st.error(f"Erro ao executar ETL: {exc}")

    # Processed files status
    st.markdown('<div class="section-title">Arquivos Processados</div>', unsafe_allow_html=True)
    files = list(PROCESSED_DIR.glob("*.parquet"))
    if files:
        rows = []
        for f in sorted(files):
            try:
                df = pd.read_parquet(f)
                rows.append({"Arquivo": f.name, "Linhas": len(df), "Colunas": len(df.columns), "Tamanho": f"{f.stat().st_size/1024:.1f} KB"})
            except Exception:
                rows.append({"Arquivo": f.name, "Linhas": "?", "Colunas": "?", "Tamanho": "?"})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("Nenhum arquivo processado encontrado. Execute o ETL acima.")


def page_agent(year: int) -> None:
    render_header(_t("header_agent"))

    # Initialize session state
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    # Reinitialize agent if year changed
    if "agent" not in st.session_state or st.session_state.get("agent_year") != year:
        try:
            from src.agents.pharma_agent import create_agent
            st.session_state.agent      = create_agent(year=year)
            st.session_state.agent_year = year
            st.session_state.chat_history = []  # clear history on year change
        except Exception as exc:
            st.error(f"Erro ao inicializar agente: {exc}")
            return

    agent = st.session_state.agent

    # Status + quota
    user_email = st.session_state.get("user_email", "")
    user_plan  = st.session_state.get("user_plan", "")

    if agent.is_available:
        st.markdown(f'<span class="badge-ok">{_t("agent_active")}</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="badge-warn">{_t("agent_fallback")}</span>', unsafe_allow_html=True)
        st.info(_t("agent_groq_hint"))

    # Quota bar
    if user_email:
        try:
            from src.agents.quota import get_user_quota
            quota = get_user_quota(user_email, user_plan)
            if not quota["unlimited"]:
                pct  = quota["pct_used"]
                used = quota["used"]
                lim  = quota["limit"]
                color = "#FF5252" if pct >= 100 else "#FFB300" if pct >= 80 else "#4DB6AC"
                st.markdown(
                    f'<div style="margin:8px 0 4px;font-size:0.82rem;color:#aaa;">Mensagens IA este mês: '
                    f'<b style="color:{color}">{used}/{lim}</b></div>'
                    f'<div style="background:#1E3A5F;border-radius:4px;height:6px;">'
                    f'<div style="background:{color};width:{min(pct,100):.0f}%;height:6px;border-radius:4px;"></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        except Exception:
            pass

    st.markdown("<br>", unsafe_allow_html=True)

    # Suggestion chips
    suggestions = TRANSLATIONS[st.session_state.get("lang", "PT")]["agent_suggestions_list"]
    st.markdown(f"**{_t('agent_suggestions')}**")
    cols = st.columns(len(suggestions))
    for col, sug in zip(cols, suggestions):
        if col.button(sug[:30] + "…" if len(sug) > 30 else sug, width="stretch"):
            st.session_state.pending_message = sug

    # Chat history
    st.markdown("---")
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">**{_t("agent_you")}:** {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)

    # Input
    user_input = st.chat_input(_t("agent_input"))

    # Handle suggestion button clicks
    if "pending_message" in st.session_state:
        user_input = st.session_state.pop("pending_message")

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.spinner(_t("agent_spinner")):
            lang = st.session_state.get("lang", "PT")
            response = agent.chat(user_input, user_email=user_email, user_plan=user_plan, lang=lang)
        st.session_state.chat_history.append({"role": "assistant", "content": response.text})
        if response.tool_calls_made:
            st.caption(f"{_t('agent_tools')}: {', '.join(response.tool_calls_made)} · {_t('agent_tokens')}: {response.tokens_used:,}")
        st.rerun()

    # Reset button
    if st.session_state.chat_history:
        if st.button(_t("agent_clear"), type="secondary"):
            st.session_state.chat_history = []
            agent.reset()
            st.rerun()


# ===========================================================================
# Sidebar & Navigation
# ===========================================================================

def sidebar() -> tuple[str, int]:
    with st.sidebar:
        # Language toggle
        lang = st.session_state.get("lang", "PT")
        col_logo, col_lang = st.columns([3, 1])
        with col_lang:
            if st.button("EN" if lang == "PT" else "PT", key="lang_toggle"):
                st.session_state["lang"] = "EN" if lang == "PT" else "PT"
                st.rerun()

        st.markdown("""
        <div style="text-align:center; padding: 0.5rem 0 0.5rem;">
          <span style="font-size:2rem;">💊</span>
          <h2 style="color:#4DB6AC; margin:0.25rem 0 0; font-size:1.2rem;">PharmaIntel BR</h2>
          <p style="color:#8899AA; font-size:0.75rem; margin:0;">v2.0</p>
        </div>
        <hr style="border-color:#1E3A5F; margin:0.75rem 0;">
        """, unsafe_allow_html=True)

        # Navigation — translated labels mapped to internal keys
        nav_labels = [_t(k) for k in _NAV_T_KEYS]
        # Preserve current page across language switches using internal key
        current_key = st.session_state.get("page_key", "overview")
        current_idx = _NAV_KEYS.index(current_key) if current_key in _NAV_KEYS else 0
        selected_idx = st.radio(
            "nav",
            options=range(len(_NAV_KEYS)),
            format_func=lambda i: nav_labels[i],
            index=current_idx,
            label_visibility="collapsed",
        )
        page_key = _NAV_KEYS[selected_idx]
        st.session_state["page_key"] = page_key

        st.markdown("<hr style='border-color:#1E3A5F;'>", unsafe_allow_html=True)
        year = st.selectbox(_t("year_label"), [2026, 2025, 2024, 2023, 2022], index=1)

        # Data status
        st.markdown(f'<p style="color:#8899AA; font-size:0.75rem; margin:0.5rem 0 0.25rem;">{_t("data_status")}</p>', unsafe_allow_html=True)
        data_files = {
            _t("nav_imports"):   f"pharma_imports_{year}.parquet",
            "KPIs":              f"kpis_anuais_{year}.parquet",
            _t("nav_companies"): "empresas_anvisa.parquet",
            _t("nav_comtrade"):  f"comtrade_{year}.parquet",
        }
        for label, fname in data_files.items():
            exists = (PROCESSED_DIR / fname).exists()
            badge = "badge-ok" if exists else "badge-warn"
            status = "OK" if exists else "Demo"
            st.markdown(f'<span class="{badge}">{label}: {status}</span><br>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # API key status
        groq_key   = bool(_secret("GROQ_API_KEY"))
        ctrade_key = bool(_secret("COMTRADE_API_KEY"))
        st.markdown(f'<p style="color:#8899AA; font-size:0.75rem; margin:0.25rem 0;">{_t("api_keys")}</p>', unsafe_allow_html=True)
        st.markdown(f'<span class="{"badge-ok" if groq_key else "badge-warn"}">Groq: {"OK" if groq_key else "Missing"}</span><br>', unsafe_allow_html=True)
        st.markdown(f'<span class="{"badge-ok" if ctrade_key else "badge-warn"}">Comtrade: {"OK" if ctrade_key else "Missing"}</span>', unsafe_allow_html=True)

        # Trial banner
        is_trial     = st.session_state.get("is_trial", False)
        trial_days   = st.session_state.get("trial_days_left", 0)
        sidebar_lang = st.session_state.get("lang", "PT")
        if is_trial:
            pct = int((trial_days / 7) * 100)
            bar_color = "#4DB6AC" if pct > 40 else ("#f0a500" if pct > 15 else "#e53935")
            trial_label = f"{'Trial' if sidebar_lang == 'EN' else 'Teste'}: {trial_days} {'days left' if sidebar_lang == 'EN' else 'dias restantes'}"
            st.markdown(f"""
            <div style="background:#112240; border:1px solid #f0a500; border-radius:8px;
                        padding:0.75rem 1rem; margin:0.5rem 0;">
              <p style="color:#f0a500; font-size:0.75rem; font-weight:600; margin:0 0 0.4rem;">
                {trial_label}
              </p>
              <div style="background:#0A1628; border-radius:4px; height:6px; overflow:hidden;">
                <div style="background:{bar_color}; width:{pct}%; height:100%; border-radius:4px;"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            upgrade_label = "Upgrade to Full Plan" if sidebar_lang == "EN" else "Fazer Upgrade"
            if st.button(upgrade_label, use_container_width=True, type="primary"):
                st.session_state["authenticated"]       = False
                st.session_state["show_pricing"]        = True
                st.session_state["show_landing"]        = False
                st.rerun()

        # Subscription info
        plan   = st.session_state.get("subscriber_plan", "")
        period = st.session_state.get("subscriber_period", "")
        if plan and not is_trial:
            from src.payments.stripe_client import PLANS, PERIOD_LABEL_PT
            plan_name   = PLANS.get(plan, {}).get("name", plan.title())
            period_name = PERIOD_LABEL_PT.get(period, period)
            st.markdown(f'<span class="badge-ok">Plano {plan_name} · {period_name}</span><br>', unsafe_allow_html=True)

            cid = st.session_state.get("stripe_customer_id", "")
            if cid:
                if st.button("Gerenciar Assinatura", use_container_width=True):
                    from src.payments.stripe_client import create_customer_portal_session
                    portal_url = create_customer_portal_session(cid, "https://pharmaintel-br.onrender.com/")
                    if portal_url:
                        st.markdown(f'<meta http-equiv="refresh" content="0; url={portal_url}">', unsafe_allow_html=True)

        # Logout
        st.markdown("<hr style='border-color:#1E3A5F; margin:1rem 0 0.5rem;'>", unsafe_allow_html=True)
        auth_user = st.session_state.get("auth_user", _APP_USERNAME)
        st.markdown(f'<p style="color:#8899AA; font-size:0.75rem; margin:0 0 0.4rem;">{_t("logged_as")} <b style="color:#4DB6AC;">{auth_user}</b></p>', unsafe_allow_html=True)
        if st.button(_t("logout"), use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state["auth_user"]     = ""
            st.session_state.pop("subscriber_plan",   None)
            st.session_state.pop("subscriber_period",  None)
            st.session_state.pop("subscriber_email",   None)
            st.session_state.pop("stripe_customer_id", None)
            st.session_state.pop("is_trial",           None)
            st.session_state.pop("trial_days_left",    None)
            st.session_state["show_landing"] = True
            st.rerun()

    return page_key, year


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    page_key, year = sidebar()

    pages = {
        "overview":   page_overview,
        "imports":    page_importacoes,
        "anvisa":     page_anvisa,
        "companies":  page_empresas,
        "comtrade":   page_comtrade,
        "etl":        page_etl,
        "agent":      page_agent,
    }

    fn = pages.get(page_key)
    if fn:
        fn(year)


if __name__ == "__main__":
    main()
