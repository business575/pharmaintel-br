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

# Keepalive disabled — UptimeRobot handles pinging externally (saves memory)
# if os.getenv("APP_ENV", "development") != "development":
#     _start_keepalive()


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

# Patent scheduler disabled on free tier to save memory — run manually from admin panel
# _start_patent_scheduler()

# Telegram bot — starts if TELEGRAM_BOT_TOKEN is set
try:
    from src.integrations.telegram_bot import start_bot as _start_telegram
    _start_telegram()
except Exception as _tg_exc:
    logger.warning("Telegram bot not started: %s", _tg_exc)

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
        "agent_active":         "Agente ATIVO",
        "agent_fallback":       "Modo Fallback — Configure a chave de IA",
        "agent_groq_hint":      "Adicione a chave de IA nas variáveis de ambiente do Render.",
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
        # Quality Control
        "nav_quality":        "Qualidade",
        "nav_costs":          "Gerente Financeiro",
        # Outreach
        "nav_outreach":       "Prospecção",
        "outreach_title":     "Agente de Prospecção — 10-20 contatos/dia",
        "outreach_run":       "Disparar emails hoje",
        "outreach_dry":       "Simular (sem enviar)",
        "outreach_seed":      "Carregar prospects iniciais",
        "outreach_pending":   "Aguardando contato",
        "outreach_contacted": "Contatados",
        "outreach_no_email":  "Sem email (adicionar manualmente)",
        # Admin Director
        "nav_director":       "Diretora IA",
        "header_director":    "Diretora IA — Centro de Comando",
        "director_goal":      "Meta",
        "director_total_leads": "Leads Totais",
        "director_hot_leads": "Leads Quentes",
        "director_revenue":   "Receita Acumulada",
        "director_days_left": "Dias Restantes",
        "director_pipeline":  "Pipeline de Vendas",
        "director_hot_table": "Leads Quentes — Prioridade de Contato",
        "director_chat":      "Chat com a Diretora IA",
        "director_run_seq":   "Executar Sequências de Email",
        "director_all_leads": "Todos os Leads",
        "director_mark_contacted": "Marcar Contatado",
        "director_draft_msg": "Rascunhar Mensagem",
        "director_brief":     "Briefing Diário",
        "director_suggestions": [
            "Qual o próximo lead para contatar?",
            "Quantos faltam para R$50k?",
            "Rascunha mensagem para o lead mais quente",
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
        "agent_active":         "Agent ACTIVE",
        "agent_fallback":       "Fallback Mode — Set AI key",
        "agent_groq_hint":      "Add the AI key to Render environment variables.",
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
        # Quality Control
        "nav_quality":        "Quality Control",
        "nav_costs":          "Finance Manager",
        # Outreach
        "nav_outreach":       "Outreach",
        "outreach_title":     "Outreach Agent — 10-20 contacts/day",
        "outreach_run":       "Send emails today",
        "outreach_dry":       "Simulate (no send)",
        "outreach_seed":      "Load initial prospects",
        "outreach_pending":   "Pending contact",
        "outreach_contacted": "Contacted",
        "outreach_no_email":  "No email (add manually)",
        # Admin Director
        "nav_director":       "AI Director",
        "header_director":    "AI Director — Command Center",
        "director_goal":      "Goal",
        "director_total_leads": "Total Leads",
        "director_hot_leads": "Hot Leads",
        "director_revenue":   "Revenue",
        "director_days_left": "Days Left",
        "director_pipeline":  "Sales Pipeline",
        "director_hot_table": "Hot Leads — Contact Priority",
        "director_chat":      "Chat with AI Director",
        "director_run_seq":   "Run Email Sequences",
        "director_all_leads": "All Leads",
        "director_mark_contacted": "Mark Contacted",
        "director_draft_msg": "Draft Message",
        "director_brief":     "Daily Briefing",
        "director_suggestions": [
            "Which lead should I contact next?",
            "How many sales to reach R$50k?",
            "Draft message for hottest lead",
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
    page_title="PharmaIntel BR | Pharmaceutical Intelligence for Brazil",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# SEO meta tags + force title override (Streamlit default title is "Streamlit")
st.markdown("""
<meta name="description" content="Pharmaceutical market intelligence platform for Brazil. Monitor pharma imports (US$24B market), track 42,000+ ANVISA registrations, and discover opportunities with AI — real Comex Stat and ANVISA data.">
<meta name="keywords" content="pharmaceutical intelligence Brazil, importação farmacêutica, ANVISA registrations, Comex Stat, NCM 30 90, pharma market Brazil, medicamentos importação, dispositivos médicos">
<meta name="author" content="PharmaIntel BR">
<meta name="robots" content="index, follow">
<meta property="og:title" content="PharmaIntel BR | Pharmaceutical Intelligence for Brazil">
<meta property="og:description" content="Monitor US$24B pharma import market, track 42,000+ ANVISA registrations and discover opportunities — real data + AI.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://pharmaceuticaai.com">
<meta property="og:site_name" content="PharmaIntel BR">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="PharmaIntel BR | Pharmaceutical Intelligence for Brazil">
<meta name="twitter:description" content="Monitor Brazil's US$24B pharma import market with real ANVISA and Comex Stat data + AI analysis.">
<script>
  // Force page title — overrides Streamlit's default "Streamlit" title
  document.title = "PharmaIntel BR | Pharmaceutical Intelligence for Brazil";
  // Keep overriding in case Streamlit resets it
  const _titleObserver = new MutationObserver(() => {
    if (document.title !== "PharmaIntel BR | Pharmaceutical Intelligence for Brazil") {
      document.title = "PharmaIntel BR | Pharmaceutical Intelligence for Brazil";
    }
  });
  _titleObserver.observe(document.querySelector("title") || document.head, {childList: true, subtree: true, characterData: true});
</script>
<!-- Google Analytics GA4 -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2B5M8XP41Z"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-2B5M8XP41Z');
</script>
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
5. REGRA CRÍTICA DE PRECISÃO: NUNCA associe um produto específico a um laboratório a menos que você tenha certeza absoluta. Erros comuns a evitar: insulina glargina é Sanofi (não Pfizer), insulina aspart é Novo Nordisk (não Sanofi), rivastigmina é Novartis (não Pfizer). Se não tiver certeza da empresa detentora da patente, diga "entre os principais detentores estão" e cite apenas os que você tem certeza. Prefira dar o panorama geral e oportunidades de mercado sem nomear empresas específicas se houver risco de erro.
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
5. CRITICAL ACCURACY RULE: NEVER associate a specific product with a laboratory unless you are absolutely certain. Common errors to avoid: insulin glargine is Sanofi (not Pfizer), insulin aspart is Novo Nordisk (not Sanofi), rivastigmine is Novartis (not Pfizer). If uncertain about patent ownership, say "among the major holders are" and only cite companies you are sure about. Prefer to give the general market overview and opportunities without naming specific companies if there is any risk of error.
6. MANDATORY TRANSPARENCY: at the start of every response, include this note in italics: "📊 *Demo mode — analysis based on AI trained knowledge (accurate but may not reflect the most recent market data). On the full platform, data comes from secure government and private sources, updated daily.*"
7. ALWAYS end with: "🔓 With full PharmaIntel platform access, I would deliver in real time:" — list 3 specific technical analyses that only exist with live data
8. Last line ALWAYS: "Subscribe now and make decisions with real data, updated daily."
9. Tone: senior technical expert — precise, direct, no exaggeration, no marketing language
10. MANDATORY LANGUAGE: always respond in ENGLISH regardless of the language the user writes in."""

DEMO_MAX_QUESTIONS = 2


def _save_demo_lead(email: str, lang: str = "PT") -> None:
    """Save demo lead to SQLite DB, Formspree, and send welcome email."""
    # 1. SQLite (local/Render — may be lost on restart)
    try:
        from src.db.database import init_db, save_demo_lead as _db_save
        init_db()
        _db_save(email=email, lang=lang, status="new", temperature="cold")
    except Exception as exc:
        logger.warning("Failed to save demo lead to DB: %s", exc)

    # 2. Formspree — persists externally even if Render restarts
    try:
        import requests as _req
        _req.post(
            "https://formspree.io/f/xrerbqbj",
            json={"email": email, "lang": lang, "origem": "demo", "status": "new"},
            headers={"Accept": "application/json"},
            timeout=8,
        )
        logger.info("Lead saved to Formspree: %s", email)
    except Exception as exc:
        logger.warning("Formspree lead save failed: %s", exc)

    # 3. Welcome email via Resend
    try:
        _send_demo_email(email, lang, "welcome")
    except Exception as exc:
        logger.warning("Welcome email failed: %s", exc)


def _send_demo_email(email: str, lang: str, kind: str) -> None:
    """Send demo-related emails via Resend API."""
    import httpx
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        return

    is_en = lang == "EN"

    if kind == "welcome":
        subject = "Your PharmaIntel AI demo is ready" if is_en else "Seu demo PharmaIntel AI está pronto"
        body = f"""
<div style="font-family:sans-serif; max-width:560px; margin:0 auto; background:#0A1628; color:#E2EAF4; padding:2rem; border-radius:12px;">
  <h2 style="color:#4DB6AC; margin-bottom:0.5rem;">PharmaIntel AI</h2>
  <p style="color:#8899AA; margin-top:0;">{"Brazil Pharmaceutical Market Intelligence" if is_en else "Inteligência de Mercado Farmacêutico Brasileiro"}</p>
  <hr style="border-color:#1E3A5F; margin:1.5rem 0;">
  <p>{"Hi," if is_en else "Olá,"}</p>
  <p>{"Your free demo is active. Ask the AI anything about the Brazilian pharma market — import flows, ANVISA registrations, patent expiries, biosimilar opportunities." if is_en else "Seu demo gratuito está ativo. Pergunte à IA qualquer coisa sobre o mercado farmacêutico brasileiro — importações, registros ANVISA, vencimento de patentes, oportunidades de biossimilares."}</p>
  <div style="text-align:center; margin:2rem 0;">
    <a href="https://pharmaintel-br.onrender.com" style="background:#00897B; color:#fff; padding:0.75rem 2rem; border-radius:8px; text-decoration:none; font-weight:700;">
      {"Open Platform" if is_en else "Abrir Plataforma"}
    </a>
  </div>
  <p style="color:#8899AA; font-size:0.85rem;">{"Questions? Reply to this email." if is_en else "Dúvidas? Responda este email."}</p>
  <p style="color:#8899AA; font-size:0.85rem;">Vinicius Figueiredo<br>PharmaIntel BR<br>Business@globalhealthcareaccess.com</p>
</div>
"""
    elif kind == "followup":
        subject = "Did the AI answer your question? Here's what else it can do" if is_en else "A IA respondeu sua dúvida? Veja o que mais ela faz"
        body = f"""
<div style="font-family:sans-serif; max-width:560px; margin:0 auto; background:#0A1628; color:#E2EAF4; padding:2rem; border-radius:12px;">
  <h2 style="color:#4DB6AC; margin-bottom:0.5rem;">PharmaIntel AI</h2>
  <hr style="border-color:#1E3A5F; margin:1.5rem 0;">
  <p>{"Hi," if is_en else "Olá,"}</p>
  <p>{"You tested the PharmaIntel AI demo. Here's what subscribers get with full access:" if is_en else "Você testou o demo do PharmaIntel AI. Veja o que os assinantes têm com acesso completo:"}</p>
  <ul style="color:#B0BEC5; line-height:2;">
    <li>{"Unlimited AI queries with real-time data" if is_en else "Consultas ilimitadas à IA com dados em tempo real"}</li>
    <li>{"ANVISA registration alerts and expiry tracking" if is_en else "Alertas de registro ANVISA e vencimentos"}</li>
    <li>{"Import dashboard: $24B in tracked flows" if is_en else "Dashboard de importações: $24B em fluxos monitorados"}</li>
    <li>{"Patent expiry windows for biosimilar entry" if is_en else "Janelas de patentes para entrada de biossimilares"}</li>
    <li>{"Government procurement opportunities" if is_en else "Oportunidades de licitações públicas"}</li>
  </ul>
  <div style="text-align:center; margin:2rem 0;">
    <a href="https://pharmaintel-br.onrender.com" style="background:#00897B; color:#fff; padding:0.75rem 2rem; border-radius:8px; text-decoration:none; font-weight:700;">
      {"See Plans & Subscribe" if is_en else "Ver Planos e Assinar"}
    </a>
  </div>
  <p style="color:#8899AA; font-size:0.85rem;">Vinicius Figueiredo<br>PharmaIntel BR<br>Business@globalhealthcareaccess.com</p>
</div>
"""
    else:
        return

    httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": "PharmaIntel AI <noreply@pharmaintel-br.onrender.com>",
            "to": [email],
            "subject": subject,
            "html": body,
        },
        timeout=10,
    )


def _call_demo_ai(question: str, history: list, is_en: bool) -> str:
    """Call AI for demo — Groq primary, Anthropic fallback. Audited by Quality Control."""
    system = _DEMO_SYSTEM_EN if is_en else _DEMO_SYSTEM_PT
    messages = history + [{"role": "user", "content": question.strip()}]
    raw_text = ""

    import requests as _req

    def _openai_compat_call(base_url: str, api_key: str, model: str) -> str:
        resp = _req.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}] + messages,
                "max_tokens": 1200,
                "temperature": 0.7,
            },
            timeout=30,
        )
        data = resp.json()
        if resp.status_code != 200:
            logger.warning("AI API error %s: %s", resp.status_code, data)
            return ""
        return data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""

    # 1. Groq (primary)
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key and not raw_text:
        try:
            raw_text = _openai_compat_call("https://api.groq.com/openai/v1", groq_key, "llama-3.3-70b-versatile")
        except Exception as exc1:
            logger.warning("Groq demo failed: %s", exc1)

    # 2. DeepSeek (fallback)
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if deepseek_key and not raw_text:
        try:
            raw_text = _openai_compat_call("https://api.deepseek.com/v1", deepseek_key, "deepseek-chat")
        except Exception as exc2:
            logger.warning("DeepSeek demo failed: %s", exc2)

    # 3. Anthropic (last resort)
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key and not raw_text:
        try:
            aresp = _req.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1200, "system": system, "messages": messages},
                timeout=30,
            )
            data = aresp.json()
            raw_text = data.get("content", [{}])[0].get("text", "") or ""
        except Exception as exc3:
            logger.warning("Anthropic demo failed: %s", exc3)

    if not raw_text:
        logger.error("All AI providers failed. GROQ_KEY=%s DEEPSEEK_KEY=%s ANTHROPIC_KEY=%s",
                     bool(groq_key), bool(deepseek_key), bool(anthropic_key))
        return ""

    # ── Quality Control audit ────────────────────────────────────────────────
    try:
        from src.quality.ai_auditor import AIOutputAuditor
        from src.db.database import log_quality_check
        lang_code = "EN" if is_en else "PT"
        auditor = AIOutputAuditor()
        result = auditor.audit(raw_text, tool_calls_made=[], module="demo_ai", lang=lang_code)
        log_quality_check(
            module="demo_ai",
            check_type="ai_output_audit",
            result=result.result_str,
            error_level=result.risk_level,
            details=result.to_details_json(),
            blocked=result.blocked,
        )
        return result.audited_text  # blocked responses replaced with warning message
    except Exception as exc_audit:
        logger.warning("Quality audit failed (returning raw): %s", exc_audit)
        return raw_text


def _page_demo_agent() -> None:
    """Demo AI agent — PHD Intel.AI avatar guided experience."""
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
    .avatar-card {
        background: linear-gradient(135deg, #0D2B45 0%, #112240 100%);
        border: 1px solid #00897B; border-radius:16px;
        padding:1.5rem; margin-bottom:1.25rem; }
    .avatar-header {
        display:flex; align-items:center; gap:1rem; margin-bottom:1rem; }
    .avatar-icon {
        width:52px; height:52px; border-radius:50%;
        background:linear-gradient(135deg,#00897B,#4DB6AC);
        display:flex; align-items:center; justify-content:center;
        font-size:1.5rem; flex-shrink:0; }
    .avatar-name { color:#4DB6AC; font-weight:700; font-size:1rem; }
    .avatar-title { color:#8899AA; font-size:0.75rem; }
    .sector-btn {
        background:#0A1628; border:1px solid #1E3A5F; border-radius:10px;
        padding:0.75rem 1rem; color:#E2EAF4; font-size:0.85rem;
        cursor:pointer; transition:all 0.2s; margin:0.25rem 0; width:100%; }
    .typing-indicator { color:#4DB6AC; font-size:0.8rem; }
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
    demo_email   = st.session_state.get("demo_email", "")
    demo_count   = st.session_state.get("demo_count", 0)
    demo_history = st.session_state.get("demo_history", [])
    demo_sector  = st.session_state.get("demo_sector", "")
    locked       = demo_count >= DEMO_MAX_QUESTIONS

    # ── Email gate ────────────────────────────────────────────────────────
    if not demo_email:
        _, col_gate, _ = st.columns([1, 2, 1])
        with col_gate:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class="avatar-card" style="text-align:center;">
              <img src="https://images.unsplash.com/photo-1559839734-2b71ea197ec2?w=120&h=120&fit=crop&crop=face" style="width:80px; height:80px; border-radius:50%; border:3px solid #00897B; margin-bottom:0.75rem; object-fit:cover;" />
              <div style="color:#4DB6AC; font-weight:700; font-size:1.3rem; margin-bottom:0.25rem;">PHD Intel.AI</div>
              <div style="color:#8899AA; font-size:0.8rem; margin-bottom:1rem;">
                {'Senior Strategic Advisor · Brazilian Pharma Market' if is_en else 'Conselheiro Estratégico Sênior · Mercado Farmacêutico Brasileiro'}
              </div>
              <div style="background:#0A1628; border-radius:10px; padding:1rem; margin-bottom:1rem; text-align:left;">
                <p style="color:#E2EAF4; font-size:0.88rem; margin:0; line-height:1.7;">
                  {'👋 Hello! I am <b>PHD Intel.AI</b>, your strategic intelligence advisor for the Brazilian pharmaceutical market.<br><br>In the next 3 minutes, I will show you a real market analysis — import data, ANVISA registrations, patents, and public procurement — tailored to your sector of interest.<br><br>Enter your email to start.' if is_en else
                   '👋 Olá! Sou <b>PHD Intel.AI</b>, seu conselheiro de inteligência estratégica para o mercado farmacêutico brasileiro.<br><br>Nos próximos 3 minutos, vou te mostrar uma análise real de mercado — dados de importação, registros ANVISA, patentes e compras públicas — personalizada para o seu setor de interesse.<br><br>Digite seu email para começar.'}
                </p>
              </div>
            </div>
            """, unsafe_allow_html=True)
            with st.form("demo_email_gate"):
                email_input = st.text_input(
                    "Email",
                    placeholder="your@email.com" if is_en else "seu@email.com",
                    label_visibility="collapsed",
                )
                btn_label = "Start Guided Analysis →" if is_en else "Iniciar Análise Guiada →"
                submitted = st.form_submit_button(btn_label, use_container_width=True, type="primary")
                if submitted:
                    if not email_input or "@" not in email_input:
                        st.error("Please enter a valid email." if is_en else "Digite um email válido.")
                    else:
                        st.session_state["demo_email"] = email_input.strip().lower()
                        _save_demo_lead(email_input.strip().lower(), lang)
                        st.rerun()
            st.markdown(f"<p style='color:#8899AA; font-size:0.72rem; text-align:center; margin-top:0.5rem;'>{'Free · No credit card · No password' if is_en else 'Grátis · Sem cartão · Sem senha'}</p>", unsafe_allow_html=True)
        st.stop()
        return

    # ── Sector selection ──────────────────────────────────────────────────
    if not demo_sector:
        _, col_s, _ = st.columns([1, 3, 1])
        with col_s:
            st.markdown(f"""
            <div class="avatar-card">
              <div class="avatar-header">
                <div class="avatar-icon">🎓</div>
                <div>
                  <div class="avatar-name">PHD Intel.AI</div>
                  <div class="avatar-title">{'Senior Strategic Advisor' if is_en else 'Conselheiro Estratégico Sênior'}</div>
                </div>
              </div>
              <p style="color:#E2EAF4; font-size:0.88rem; line-height:1.7; margin:0;">
                {'Welcome! To deliver the most relevant analysis, <b>choose your sector of interest</b>. I will run a complete market intelligence report in real time.' if is_en else
                 'Bem-vindo! Para entregar a análise mais relevante, <b>escolha seu setor de interesse</b>. Vou rodar um relatório completo de inteligência de mercado em tempo real.'}
              </p>
            </div>
            """, unsafe_allow_html=True)

            sectors_pt = [
                ("💉", "Insulina e Biossimilares", "insulin"),
                ("🔬", "Oncológicos", "oncology"),
                ("🫀", "Dispositivos Médicos", "devices"),
                ("💊", "Antibióticos e Anti-infecciosos", "antibiotics"),
                ("🧠", "Neurológicos e Psiquiátricos", "neuro"),
                ("🌿", "Fitoterápicos e Genéricos", "generics"),
            ]
            sectors_en = [
                ("💉", "Insulin & Biosimilars", "insulin"),
                ("🔬", "Oncologicals", "oncology"),
                ("🫀", "Medical Devices", "devices"),
                ("💊", "Antibiotics & Anti-infectives", "antibiotics"),
                ("🧠", "Neurological & Psychiatric", "neuro"),
                ("🌿", "Phytotherapics & Generics", "generics"),
            ]
            sectors = sectors_en if is_en else sectors_pt

            st.markdown("<br>", unsafe_allow_html=True)
            for icon, label, key in sectors:
                if st.button(f"{icon}  {label}", key=f"sector_{key}", use_container_width=True):
                    st.session_state["demo_sector"] = key
                    st.session_state["demo_sector_label"] = label
                    # Auto-trigger first analysis
                    sector_questions = {
                        "insulin":     "Qual o mercado de insulina e biossimilares no Brasil? Quem são os maiores importadores, qual o tamanho do mercado em USD, e quais oportunidades de patentes vencem nos próximos 3 anos?" if not is_en else "What is the insulin and biosimilar market in Brazil? Who are the biggest importers, what is the market size in USD, and which patent opportunities expire in the next 3 years?",
                        "oncology":    "Qual o mercado de oncológicos no Brasil? Quais NCMs cresceram mais, quem domina as importações e quais oportunidades existem para novos entrantes?" if not is_en else "What is the oncology market in Brazil? Which HS codes grew the most, who dominates imports, and what opportunities exist for new entrants?",
                        "devices":     "Qual o mercado de dispositivos médicos no Brasil (capítulo 90)? Quais categorias crescem mais, quais os principais países fornecedores e como está a regulação ANVISA?" if not is_en else "What is the medical devices market in Brazil (chapter 90)? Which categories grow the most, what are the main supplier countries, and how is ANVISA regulation?",
                        "antibiotics": "Qual o mercado de antibióticos e anti-infecciosos no Brasil? Quais os principais NCMs, maiores importadores e oportunidades de mercado?" if not is_en else "What is the antibiotics and anti-infectives market in Brazil? What are the main HS codes, biggest importers, and market opportunities?",
                        "neuro":       "Qual o mercado de medicamentos neurológicos e psiquiátricos no Brasil? Quais moléculas têm maior volume de importação e quais patentes vencem em breve?" if not is_en else "What is the neurological and psychiatric drugs market in Brazil? Which molecules have the highest import volume and which patents expire soon?",
                        "generics":    "Qual o mercado de genéricos e fitoterápicos no Brasil? Quais as maiores oportunidades para importadores e como está a concorrência por NCM?" if not is_en else "What is the generics and phytotherapics market in Brazil? What are the biggest opportunities for importers and how is competition by HS code?",
                    }
                    st.session_state["demo_auto_question"] = sector_questions.get(key, "")
                    st.rerun()
        st.stop()
        return

    # ── Auto-run first analysis when sector is selected ───────────────────
    auto_q = st.session_state.pop("demo_auto_question", "")
    if auto_q and demo_count == 0 and not demo_history:
        with st.spinner("🎓 PHD Intel.AI analisando..." if not is_en else "🎓 PHD Intel.AI analyzing..."):
            answer = _call_demo_ai(auto_q, [], is_en)
        if answer:
            demo_history.append({"q": auto_q, "a": answer})
            st.session_state["demo_history"] = demo_history
            st.session_state["demo_count"]   = 1
        st.rerun()

    # ── Avatar header ─────────────────────────────────────────────────────
    sector_label = st.session_state.get("demo_sector_label", "")
    remaining = max(0, DEMO_MAX_QUESTIONS - demo_count)
    st.markdown(f"""
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:1.25rem;">
      <div style="display:flex; align-items:center; gap:0.75rem;">
        <img src="https://images.unsplash.com/photo-1559839734-2b71ea197ec2?w=80&h=80&fit=crop&crop=face" style="width:44px; height:44px; border-radius:50%; border:2px solid #00897B; object-fit:cover; flex-shrink:0;" />
        <div>
          <div style="color:#4DB6AC; font-weight:700; font-size:0.95rem;">PHD Intel.AI</div>
          <div style="color:#8899AA; font-size:0.72rem;">{sector_label}</div>
        </div>
      </div>
      <div style="background:#0D2B45; border:1px solid #1E3A5F; border-radius:8px; padding:0.3rem 0.75rem; font-size:0.75rem; color:#8899AA;">
        {'⚡ ' + str(remaining) + ' question' + ('s' if remaining != 1 else '') + ' remaining' if is_en else '⚡ ' + str(remaining) + ' pergunta' + ('s' if remaining != 1 else '') + ' restante' + ('s' if remaining != 1 else '')}
      </div>
    </div>
    <div style="background:#0D2B45; border:1px solid #1E3A5F; border-radius:8px; padding:0.5rem 1rem; margin-bottom:1rem; font-size:0.75rem; color:#8899AA;">
      📊 {'Demo mode — AI trained knowledge. Full platform: real government data updated daily.' if is_en else 'Modo demo — conhecimento treinado da IA. Plataforma completa: dados governamentais reais atualizados diariamente.'}
    </div>
    """, unsafe_allow_html=True)

    # Show conversation history
    for turn in demo_history:
        st.markdown(f'<div class="demo-bubble-user">🔍 {turn["q"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="demo-bubble-ai"><b>🎓 PHD Intel.AI</b><br><br>{turn["a"]}</div>', unsafe_allow_html=True)

    # Input form or upgrade wall
    if not locked:
        q_placeholder = "Ask a follow-up question about this sector..." if is_en else "Faça uma pergunta de acompanhamento sobre este setor..."
        send_label    = "Ask PHD Intel.AI →" if is_en else "Perguntar ao PHD Intel.AI →"

        # Follow-up suggestions
        followup_suggestions = {
            "insulin":     ["Qual o preço médio nas licitações públicas?", "Quais biossimilares podem entrar em 2026?", "Como registrar insulina na ANVISA?"],
            "oncology":    ["Quais NCMs de oncológicos cresceram mais?", "Qual o custo de importação médio?", "Há oportunidades de biossimilares oncológicos?"],
            "devices":     ["Quais dispositivos têm maior crescimento?", "Como é a classificação de risco ANVISA?", "Quais países fornecem mais?"],
            "antibiotics": ["Quais antibióticos têm maior volume?", "Como está a dependência de IFAs da China?", "Quais genéricos têm oportunidade?"],
            "neuro":       ["Quais moléculas neurológicas crescem mais?", "Há oportunidades de genéricos em 2026?", "Como é a regulação para psicotrópicos?"],
            "generics":    ["Quais genéricos têm maior margem?", "Como competir com produtos chineses?", "Quais NCMs têm menor concorrência?"],
        }
        suggestions = followup_suggestions.get(demo_sector, [])
        if suggestions and demo_count == 1:
            st.markdown(f"<p style='color:#8899AA; font-size:0.78rem; margin-bottom:0.4rem;'>{'Continue exploring:' if is_en else 'Continue explorando:'}</p>", unsafe_allow_html=True)
            cols = st.columns(len(suggestions))
            for i, sug in enumerate(suggestions):
                with cols[i]:
                    if st.button(sug, key=f"sug_{i}", use_container_width=True):
                        st.session_state["demo_quick_q"] = sug
                        st.rerun()

        # Handle quick question click
        quick_q = st.session_state.pop("demo_quick_q", "")
        if quick_q:
            with st.spinner("🎓 PHD Intel.AI analisando..." if not is_en else "🎓 PHD Intel.AI analyzing..."):
                history_msgs = []
                for turn in demo_history:
                    history_msgs.append({"role": "user", "content": turn["q"]})
                    history_msgs.append({"role": "assistant", "content": turn["a"]})
                answer = _call_demo_ai(quick_q, history_msgs, is_en)
            if answer:
                demo_history.append({"q": quick_q, "a": answer})
                st.session_state["demo_history"] = demo_history
                st.session_state["demo_count"]   = demo_count + 1
            st.rerun()

        with st.form("demo_form"):
            question = st.text_area("question", placeholder=q_placeholder, height=80, label_visibility="collapsed")
            submitted = st.form_submit_button(send_label, use_container_width=True, type="primary")
            if submitted and question.strip():
                with st.spinner("🎓 PHD Intel.AI analisando..." if not is_en else "🎓 PHD Intel.AI analyzing..."):
                    history_msgs = []
                    for turn in demo_history:
                        history_msgs.append({"role": "user", "content": turn["q"]})
                        history_msgs.append({"role": "assistant", "content": turn["a"]})
                    answer = _call_demo_ai(question.strip(), history_msgs, is_en)
                if not answer:
                    st.error("Unable to process. Contact: Business@globalhealthcareaccess.com" if is_en else "Não foi possível processar. Contato: Business@globalhealthcareaccess.com")
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
              <div style="color:#E2EAF4; font-size:1.3rem; font-weight:700; margin:0.25rem 0;">{'US$ 299' if is_en else 'R$ 497'}<span style="color:#8899AA; font-size:0.7rem;">/{'mo' if is_en else 'mês'}</span></div>
              <div style="color:#8899AA; font-size:0.72rem;">{'Strategic Intelligence' if is_en else 'Inteligência Estratégica'}</div>
            </div>
            <div style="background:#0A1628; border:2px solid #00897B; border-radius:10px; padding:1rem 1.5rem; min-width:140px;">
              <div style="color:#00897B; font-weight:700; font-size:0.9rem;">Pro ★</div>
              <div style="color:#E2EAF4; font-size:1.3rem; font-weight:700; margin:0.25rem 0;">{'US$ 499' if is_en else 'R$ 997'}<span style="color:#8899AA; font-size:0.7rem;">/{'mo' if is_en else 'mês'}</span></div>
              <div style="color:#8899AA; font-size:0.72rem;">{'Advanced Strategic AI' if is_en else 'IA Avançada Estratégica'}</div>
            </div>
            <div style="background:#0A1628; border:1px solid #26C6DA; border-radius:10px; padding:1rem 1.5rem; min-width:140px;">
              <div style="color:#26C6DA; font-weight:700; font-size:0.9rem;">Enterprise</div>
              <div style="color:#E2EAF4; font-size:1.3rem; font-weight:700; margin:0.25rem 0;">{'US$ 1,499' if is_en else 'R$ 2.497'}<span style="color:#8899AA; font-size:0.7rem;">/{'mo' if is_en else 'mês'}</span></div>
              <div style="color:#8899AA; font-size:0.72rem;">{'PhD AI · 99% Accuracy' if is_en else 'IA PhD · 99% Precisão'}</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        # Send follow-up email once when demo locks
        if not st.session_state.get("demo_followup_sent") and demo_email:
            try:
                _send_demo_email(demo_email, lang, "followup")
                st.session_state["demo_followup_sent"] = True
            except Exception:
                pass

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
            ("🤖", "Strategic Intelligence" if is_en else "Inteligência Estratégica"),
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
              <div class="price-tag">{price_info['usd_label'] if is_en else price_info['label']}</div>
              <div class="price-period">{price_info['period_label'] if not is_en else price_info['period_label'].replace('por mês','/ month').replace('a cada 3 meses','/ quarter').replace('a cada 6 meses','/ 6 months').replace('por ano','/ year')}</div>
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

    # Telegram Assistant Banner
    st.markdown("<br>", unsafe_allow_html=True)
    if is_en:
        st.markdown("""
        <div style="background:#112240; border:2px solid #4DB6AC; border-radius:12px;
                    padding:1.5rem 2rem; text-align:center; max-width:700px; margin:0 auto;">
          <div style="font-size:2rem; margin-bottom:0.5rem;">💬</div>
          <h3 style="color:#4DB6AC; margin:0 0 0.5rem;">AI Assistant on Telegram & WhatsApp</h3>
          <p style="color:#B0BEC5; font-size:0.88rem; line-height:1.6; margin:0 0 0.75rem;">
            Each <b style="color:#E2EAF4;">Starter and Pro subscriber</b> gets
            <b style="color:#E2EAF4;">1 dedicated AI assistant</b> on Telegram and WhatsApp.<br>
            Ask market questions, get alerts and receive insights — without opening the platform.
          </p>
          <p style="color:#8899AA; font-size:0.8rem; margin:0;">
            ✅ 1 assistant per subscriber &nbsp;·&nbsp; ✅ Real data &nbsp;·&nbsp; ✅ Included in your plan
          </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:#112240; border:2px solid #4DB6AC; border-radius:12px;
                    padding:1.5rem 2rem; text-align:center; max-width:700px; margin:0 auto;">
          <div style="font-size:2rem; margin-bottom:0.5rem;">💬</div>
          <h3 style="color:#4DB6AC; margin:0 0 0.5rem;">Assistente IA no Telegram e WhatsApp</h3>
          <p style="color:#B0BEC5; font-size:0.88rem; line-height:1.6; margin:0 0 0.75rem;">
            Cada assinante <b style="color:#E2EAF4;">Starter e Pro</b> recebe
            <b style="color:#E2EAF4;">1 assistente IA exclusivo</b> no Telegram e WhatsApp.<br>
            Faça perguntas de mercado, receba alertas e insights — sem abrir a plataforma.
          </p>
          <p style="color:#8899AA; font-size:0.8rem; margin:0;">
            ✅ 1 assistente por assinante &nbsp;·&nbsp; ✅ Dados reais &nbsp;·&nbsp; ✅ Incluso no plano
          </p>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

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

    # ── 3D Spinning Globe (globe.gl) ─────────────────────────────────────────
    import streamlit.components.v1 as _components
    _components.html("""
<!DOCTYPE html>
<html>
<head>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background: #0A1628; overflow: hidden; }
  #globe-wrap {
    width: 100vw; height: 480px;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    background: radial-gradient(ellipse at center, #0D2B45 0%, #0A1628 70%);
  }
  #globeViz { flex: 1; width: 100%; }
  .brand {
    padding: 10px 0 18px;
    text-align: center;
    font-family: 'Segoe UI', Arial, sans-serif;
  }
  .brand-name {
    font-size: 1.55rem; font-weight: 800; letter-spacing: 0.04em;
    background: linear-gradient(90deg, #4DB6AC, #26C6DA, #80CBC4);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .brand-tag {
    font-size: 0.78rem; color: #8899AA; letter-spacing: 0.12em;
    text-transform: uppercase; margin-top: 3px;
  }
</style>
</head>
<body>
<div id="globe-wrap">
  <div id="globeViz"></div>
  <div class="brand">
    <div class="brand-name">💊 PharmaIntel AI</div>
    <div class="brand-tag">Pharmaceutical Intelligence · Brazilian Market</div>
  </div>
</div>

<script src="https://unpkg.com/globe.gl@2.27.2/dist/globe.gl.min.js"></script>
<script>
const PHARMA_HUBS = [
  { lat: -15.8, lng: -47.9, label: 'Brazil 🇧🇷', size: 0.7, color: '#4DB6AC', city: 'Brasília' },
  { lat: -23.5, lng: -46.6, label: 'São Paulo 🇧🇷', size: 0.55, color: '#4DB6AC', city: 'São Paulo' },
  { lat: 28.6,  lng: 77.2,  label: 'India 🇮🇳',   size: 0.5,  color: '#26C6DA', city: 'New Delhi' },
  { lat: 19.0,  lng: 72.8,  label: 'Mumbai 🇮🇳',  size: 0.45, color: '#26C6DA', city: 'Mumbai' },
  { lat: 31.2,  lng: 121.5, label: 'China 🇨🇳',   size: 0.5,  color: '#26C6DA', city: 'Shanghai' },
  { lat: 39.9,  lng: 116.4, label: 'Beijing 🇨🇳', size: 0.4,  color: '#26C6DA', city: 'Beijing' },
  { lat: 52.5,  lng: 13.4,  label: 'Germany 🇩🇪', size: 0.4,  color: '#80CBC4', city: 'Berlin' },
  { lat: 40.7,  lng: -74.0, label: 'USA 🇺🇸',     size: 0.45, color: '#80CBC4', city: 'New York' },
  { lat: 47.4,  lng: 8.5,   label: 'Switzerland 🇨🇭', size: 0.38, color: '#80CBC4', city: 'Zurich' },
  { lat: 35.7,  lng: 139.7, label: 'Japan 🇯🇵',   size: 0.35, color: '#B2DFDB', city: 'Tokyo' },
  { lat: 51.5,  lng: -0.1,  label: 'UK 🇬🇧',      size: 0.38, color: '#B2DFDB', city: 'London' },
  { lat: 48.9,  lng: 2.3,   label: 'France 🇫🇷',  size: 0.35, color: '#B2DFDB', city: 'Paris' },
];

// Arcs: Brazil <-> each hub
const ARCS = PHARMA_HUBS.filter(h => h.city !== 'Brasília' && h.city !== 'São Paulo').map(h => ({
  startLat: -15.8, startLng: -47.9,
  endLat: h.lat,   endLng: h.lng,
  color: ['#4DB6AC88', h.color + '88'],
  label: `Brasil → ${h.city}`,
}));

const globe = Globe()
  .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg')
  .bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png')
  .backgroundImageUrl('https://unpkg.com/three-globe/example/img/night-sky.png')
  .atmosphereColor('#4DB6AC')
  .atmosphereAltitude(0.18)
  // Points
  .pointsData(PHARMA_HUBS)
  .pointLat('lat')
  .pointLng('lng')
  .pointColor('color')
  .pointAltitude(0.06)
  .pointRadius('size')
  .pointLabel(d => `<div style="background:#0D2B45;border:1px solid #4DB6AC;border-radius:8px;padding:6px 12px;color:#E2EAF4;font-family:Arial;font-size:13px;">${d.label}</div>`)
  // Arcs
  .arcsData(ARCS)
  .arcStartLat('startLat').arcStartLng('startLng')
  .arcEndLat('endLat').arcEndLng('endLng')
  .arcColor('color')
  .arcAltitude(0.25)
  .arcStroke(0.5)
  .arcDashLength(0.4)
  .arcDashGap(0.15)
  .arcDashAnimateTime(2200)
  (document.getElementById('globeViz'));

// Auto-rotate
globe.controls().autoRotate = true;
globe.controls().autoRotateSpeed = 0.6;
globe.controls().enableZoom = false;

// Start pointing at Brazil
globe.pointOfView({ lat: -15, lng: -47, altitude: 2.2 }, 0);

// Responsive
window.addEventListener('resize', () => {
  globe.width(document.getElementById('globeViz').offsetWidth);
});
</script>
</body>
</html>
    """, height=490, scrolling=False)

    # Hero
    if is_en:
        hero_html = """
        <div style="text-align:center; padding: 1rem 1rem 1.5rem;">
          <div class="hero-title">
            Identify Million-Dollar Opportunities<br>
            <span class="hero-accent">in Brazil's $24B Pharma Import Market</span>
          </div>
          <p class="hero-sub">
            The only AI platform built exclusively for the Brazilian pharma import market.<br>
            Know <b style="color:#E2EAF4;">who is importing, how much, at what price, and where to enter.</b>
          </p>
        </div>"""
    else:
        hero_html = """
        <div style="text-align:center; padding: 1rem 1rem 1.5rem;">
          <div class="hero-title">
            Identifique Oportunidades de Milhões<br>
            <span class="hero-accent">no Mercado Farmacêutico Brasileiro de US$ 24 Bilhões</span>
          </div>
          <p class="hero-sub">
            A única plataforma de IA construída exclusivamente para o mercado farmacêutico brasileiro.<br>
            Saiba <b style="color:#E2EAF4;">quem importa, quanto, a que preço e onde entrar.</b>
          </p>
        </div>"""
    st.markdown(hero_html, unsafe_allow_html=True)

    # ── Case Real ─────────────────────────────────────────────────────────────
    if is_en:
        case_html = """
        <div style="background:#112240; border:1px solid #00897B; border-radius:12px;
                    padding:1.25rem 1.5rem; margin:0 0 1.5rem; max-width:900px; margin-left:auto; margin-right:auto;">
          <p style="color:#4DB6AC; font-size:0.78rem; font-weight:700; letter-spacing:1px; margin:0 0 0.75rem;">
            💡 REAL EXAMPLE — AI ANSWER IN SECONDS
          </p>
          <p style="color:#8899AA; font-size:0.82rem; margin:0 0 0.5rem;">
            <i>Question asked: "Who are the top insulin importers in Brazil and what are government purchase prices?"</i>
          </p>
          <p style="color:#E2EAF4; font-size:0.85rem; line-height:1.7; margin:0;">
            🔹 <b>Top importers:</b> Sanofi, Novo Nordisk, Eli Lilly — combined US$1.2B in 2025<br>
            🔹 <b>Government price (BPS):</b> Insulin Glargine avg R$42.80/unit — 8,300 government purchases tracked<br>
            🔹 <b>Opportunity:</b> Patent window opens for biosimilar entry in 2026 — 3 molecules identified<br>
            🔹 <b>ANVISA status:</b> 12 active registrations, 2 expiring in 90 days
          </p>
        </div>"""
    else:
        case_html = """
        <div style="background:#112240; border:1px solid #00897B; border-radius:12px;
                    padding:1.25rem 1.5rem; margin:0 0 1.5rem; max-width:900px; margin-left:auto; margin-right:auto;">
          <p style="color:#4DB6AC; font-size:0.78rem; font-weight:700; letter-spacing:1px; margin:0 0 0.75rem;">
            💡 EXEMPLO REAL — RESPOSTA DA IA EM SEGUNDOS
          </p>
          <p style="color:#8899AA; font-size:0.82rem; margin:0 0 0.5rem;">
            <i>Pergunta: "Quais os maiores importadores de insulina no Brasil e quais os preços de compra pública?"</i>
          </p>
          <p style="color:#E2EAF4; font-size:0.85rem; line-height:1.7; margin:0;">
            🔹 <b>Maiores importadores:</b> Sanofi, Novo Nordisk, Eli Lilly — juntos US$ 1,2 bi em 2025<br>
            🔹 <b>Preço governo (BPS):</b> Insulina Glargina média R$ 42,80/unidade — 8.300 compras rastreadas<br>
            🔹 <b>Oportunidade:</b> Janela de patente abre para biossimilares em 2026 — 3 moléculas identificadas<br>
            🔹 <b>Status ANVISA:</b> 12 registros ativos, 2 vencendo em 90 dias
          </p>
        </div>"""
    st.markdown(case_html, unsafe_allow_html=True)

    # Stats
    s1, s2, s3, s4 = st.columns(4)
    stats = [
        ("US$ 24.09B", "Pharma Imports · 2025"       if is_en else "Importações Farmacêuticas · 2025"),
        ("42.926",     "ANVISA Registrations"         if is_en else "Registros ANVISA"),
        ("8.500+",     "Active Importers"             if is_en else "Importadores Ativos"),
        ("208",        "NCM/HS Codes Monitored"       if is_en else "NCMs Monitorados"),
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
                ("📊", "Know who is winning",      "See every importer by NCM, volume, price and country of origin — real Comex Stat data"),
                ("🏛️", "Avoid regulatory risk",    "Track 42,000+ ANVISA registrations, expiry alerts and compliance status in real time"),
                ("🤖", "Get answers in seconds",   "Ask the AI anything — market share, pricing, competitors, opportunities — no analyst needed"),
                ("💰", "Find government contracts","US$24B in government procurement tracked — identify buyers before your competitors do"),
                ("🏢", "Map your competition",     "8,500+ active importers with full product portfolio and market share analysis"),
                ("🧬", "Catch patent windows",     "Biosimilar entry opportunities identified automatically as patents expire"),
            ]
        else:
            features = [
                ("📊", "Saiba quem está ganhando", "Veja cada importador por NCM, volume, preço e origem — dados reais Comex Stat"),
                ("🏛️", "Evite risco regulatório",  "Monitore 42.000+ registros ANVISA, vencimentos e status de compliance em tempo real"),
                ("🤖", "Respostas em segundos",    "Pergunte qualquer coisa à IA — market share, preços, concorrentes — sem analista"),
                ("💰", "Encontre contratos públicos","US$ 24 bi em licitações rastreados — identifique compradores antes dos concorrentes"),
                ("🏢", "Mapeie a concorrência",    "8.500+ importadores ativos com portfólio completo e análise de market share"),
                ("🧬", "Capture janelas de patente","Oportunidades de biossimilares identificadas automaticamente ao vencer patentes"),
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
          {"2 free questions · No credit card · No sign-up" if is_en else "2 perguntas grátis · Sem cartão · Sem cadastro"}
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

    # Inject demo ANVISA compliance columns if ETL hasn't run yet
    if "anvisa_ativo" not in df.columns and not df.empty:
        import numpy as _np
        _rng = _np.random.default_rng(42)
        df = df.copy()
        df["anvisa_ativo"]       = _rng.choice([True, False], size=len(df), p=[0.84, 0.16])
        df["risco_regulatorio"]  = _np.where(df["anvisa_ativo"], _rng.uniform(0, 3, len(df)), _rng.uniform(5, 10, len(df)))
        is_demo = True

    # Compliance summary
    if "anvisa_ativo" in df.columns:
        n_total  = len(df)
        n_ativo  = int(df["anvisa_ativo"].sum())
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
# Quality Control Page
# ===========================================================================

def _page_quality(_year: int = 2025) -> None:
    """Admin-only Quality Control dashboard — monitors data and AI output accuracy."""
    lang = st.session_state.get("lang", "PT")
    is_en = lang == "EN"

    title = "Quality Control — Head of Quality" if is_en else "Controle de Qualidade — Gerente de Qualidade"
    st.markdown(f'<h2 style="color:#4DB6AC;">{title}</h2>', unsafe_allow_html=True)

    from src.db.database import init_db, get_quality_summary, get_quality_logs
    init_db()

    # Time range
    hours_opts = [1, 6, 24, 48, 168]
    hours_labels = ["1h", "6h", "24h", "48h", "7 dias"]
    hours = st.selectbox(
        "Período" if not is_en else "Period",
        options=hours_opts,
        format_func=lambda h: hours_labels[hours_opts.index(h)],
        index=2,
    )

    summary = get_quality_summary(since_hours=hours)
    logs    = get_quality_logs(limit=300, since_hours=hours)

    # ── KPI Cards ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    kpi = 'style="background:#112240;border:1px solid #1E3A5F;border-radius:10px;padding:1rem;text-align:center;margin:0.25rem;"'

    with k1:
        acc = summary.get("accuracy_pct", 100.0)
        color = "#4DB6AC" if acc >= 99 else ("#f0a500" if acc >= 90 else "#e53935")
        label = "Accuracy Rate" if is_en else "Taxa de Precisão"
        target = "Target: ≥99%"
        st.markdown(f'<div {kpi}><p style="color:#8899AA;font-size:0.75rem;margin:0;">{label}</p>'
                    f'<h2 style="color:{color};margin:0.25rem 0 0;">{acc:.1f}%</h2>'
                    f'<p style="color:#556;font-size:0.68rem;margin:0;">{target}</p></div>',
                    unsafe_allow_html=True)
    with k2:
        crit = summary.get("critical", 0)
        color = "#e53935" if crit > 0 else "#4DB6AC"
        label = "Critical Errors" if is_en else "Erros Críticos"
        st.markdown(f'<div {kpi}><p style="color:#8899AA;font-size:0.75rem;margin:0;">{label}</p>'
                    f'<h2 style="color:{color};margin:0.25rem 0 0;">{crit}</h2>'
                    f'<p style="color:#556;font-size:0.68rem;margin:0;">Target: 0</p></div>',
                    unsafe_allow_html=True)
    with k3:
        blk = summary.get("blocked", 0)
        color = "#f0a500" if blk > 0 else "#4DB6AC"
        label = "Blocked Outputs" if is_en else "Outputs Bloqueados"
        st.markdown(f'<div {kpi}><p style="color:#8899AA;font-size:0.75rem;margin:0;">{label}</p>'
                    f'<h2 style="color:{color};margin:0.25rem 0 0;">{blk}</h2>'
                    f'<p style="color:#556;font-size:0.68rem;margin:0;">{"100% detected" if is_en else "100% detectados"}</p></div>',
                    unsafe_allow_html=True)
    with k4:
        total = summary.get("total", 0)
        passed = summary.get("pass", 0)
        cons = round(passed / total * 100, 1) if total > 0 else 100.0
        color = "#4DB6AC" if cons >= 95 else "#f0a500"
        label = "Consistency" if is_en else "Consistência"
        st.markdown(f'<div {kpi}><p style="color:#8899AA;font-size:0.75rem;margin:0;">{label}</p>'
                    f'<h2 style="color:{color};margin:0.25rem 0 0;">{cons:.1f}%</h2>'
                    f'<p style="color:#556;font-size:0.68rem;margin:0;">Target: ≥99%</p></div>',
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Module breakdown ──────────────────────────────────────────────────────
    by_module = summary.get("by_module", {})
    if by_module:
        st.markdown(f'### {"Breakdown by Module" if is_en else "Breakdown por Módulo"}')
        try:
            import plotly.graph_objects as go
            module_names = list(by_module.keys())
            pass_v = [by_module[m].get("pass", 0) for m in module_names]
            fail_v = [by_module[m].get("fail", 0) for m in module_names]
            warn_v = [by_module[m].get("warn", 0) for m in module_names]
            fig = go.Figure(data=[
                go.Bar(name="Pass", x=module_names, y=pass_v, marker_color="#4DB6AC"),
                go.Bar(name="Warn", x=module_names, y=warn_v, marker_color="#f0a500"),
                go.Bar(name="Fail", x=module_names, y=fail_v, marker_color="#e53935"),
            ])
            fig.update_layout(
                barmode="stack", paper_bgcolor="#0A1628", plot_bgcolor="#0A1628",
                font_color="#E2EAF4", legend=dict(orientation="h"),
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.json(by_module)
    else:
        st.info("Nenhum log de qualidade no período selecionado. As verificações são geradas automaticamente ao usar a plataforma."
                if not is_en else
                "No quality logs in the selected period. Checks are generated automatically when using the platform.")

    # ── Log table ─────────────────────────────────────────────────────────────
    st.markdown(f'### {"Recent Quality Log" if is_en else "Log de Qualidade Recente"}')
    modules = ["Todos" if not is_en else "All", "imports_data", "anvisa_data", "ai_output", "demo_ai"]
    mod_filter = st.selectbox("Módulo" if not is_en else "Module", modules)
    filtered = [
        r for r in logs
        if mod_filter in ("Todos", "All") or r["module"] == mod_filter
    ]

    if filtered:
        import pandas as _pd
        df_log = _pd.DataFrame(filtered)[
            ["timestamp", "module", "check_type", "result", "error_level", "blocked"]
        ]
        df_log["timestamp"] = df_log["timestamp"].str[:19]

        def _color_result(val):
            return {"pass": "color: #4DB6AC", "fail": "color: #e53935", "warn": "color: #f0a500"}.get(val, "")

        st.dataframe(
            df_log.style.map(_color_result, subset=["result"]),
            use_container_width=True, height=380, hide_index=True,
        )

        # Detail expander for flagged rows
        flagged = [r for r in filtered if r["result"] != "pass"]
        if flagged:
            label = f"Ver detalhes ({len(flagged)} alertas/erros)" if not is_en else f"View details ({len(flagged)} alerts/errors)"
            with st.expander(label):
                for r in flagged[:20]:
                    lvl_color = {"critical": "#e53935", "medium": "#f0a500", "low": "#4DB6AC"}.get(r["error_level"], "#fff")
                    st.markdown(
                        f'<span style="color:{lvl_color}">●</span> '
                        f'**{r["module"]} · {r["check_type"]}** — `{r["result"]}` (nível: {r["error_level"]})',
                        unsafe_allow_html=True,
                    )
                    if r.get("details"):
                        try:
                            import json as _json
                            st.json(_json.loads(r["details"]))
                        except Exception:
                            st.text(r["details"])
                    st.markdown("---")
    else:
        st.info("Nenhum registro no filtro selecionado." if not is_en else "No records for selected filter.")

    # ── Manual data validation trigger ───────────────────────────────────────
    st.markdown("---")
    st.markdown(f'### {"Manual Validation" if is_en else "Validação Manual"}')
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Validar dados de importação" if not is_en else "🔍 Validate import data", use_container_width=True):
            with st.spinner("Validando..." if not is_en else "Validating..."):
                try:
                    from src.quality.data_validator import PharmaDataValidator
                    from src.db.database import log_quality_check
                    vr_path = PROCESSED_DIR / f"pharma_imports_2025.parquet"
                    if vr_path.exists():
                        import pandas as _pd2
                        df_imp = _pd2.read_parquet(vr_path)
                        validator = PharmaDataValidator()
                        vr = validator.validate_dataframe(df_imp, module="imports_data")
                        log_quality_check(
                            module="imports_data", check_type="manual_validation",
                            result=vr.result_str, error_level=vr.error_level,
                            details=vr.to_details_json(), blocked=False,
                        )
                        color = "#4DB6AC" if vr.passed else "#e53935"
                        st.markdown(f'<span style="color:{color}">**Score: {vr.score}/100 — {vr.result_str.upper()}**</span>', unsafe_allow_html=True)
                        if vr.errors:
                            for e in vr.errors: st.error(e)
                        if vr.warnings:
                            for w in vr.warnings: st.warning(w)
                    else:
                        st.warning("Arquivo pharma_imports_2025.parquet não encontrado.")
                except Exception as exc:
                    st.error(f"Erro: {exc}")
    with col2:
        if st.button("🔍 Validar dados ANVISA" if not is_en else "🔍 Validate ANVISA data", use_container_width=True):
            with st.spinner("Validando..." if not is_en else "Validating..."):
                try:
                    from src.quality.data_validator import PharmaDataValidator
                    from src.db.database import log_quality_check
                    vr_path = PROCESSED_DIR / "anvisa_medicamentos.parquet"
                    if vr_path.exists():
                        import pandas as _pd2
                        df_anv = _pd2.read_parquet(vr_path)
                        validator = PharmaDataValidator()
                        vr = validator.validate_dataframe(df_anv, module="anvisa_data")
                        log_quality_check(
                            module="anvisa_data", check_type="manual_validation",
                            result=vr.result_str, error_level=vr.error_level,
                            details=vr.to_details_json(), blocked=False,
                        )
                        color = "#4DB6AC" if vr.passed else "#e53935"
                        st.markdown(f'<span style="color:{color}">**Score: {vr.score}/100 — {vr.result_str.upper()}**</span>', unsafe_allow_html=True)
                        if vr.errors:
                            for e in vr.errors: st.error(e)
                        if vr.warnings:
                            for w in vr.warnings: st.warning(w)
                    else:
                        st.warning("Arquivo anvisa_medicamentos.parquet não encontrado.")
                except Exception as exc:
                    st.error(f"Erro: {exc}")


# ===========================================================================
# Outreach Agent Page
# ===========================================================================

def _page_outreach(_year: int = 2025) -> None:
    """Admin-only outreach agent — prospect management and daily email dispatch."""
    lang = st.session_state.get("lang", "PT")
    is_en = lang == "EN"

    st.markdown(f'<h2 style="color:#4DB6AC;">{_t("outreach_title")}</h2>', unsafe_allow_html=True)

    from src.db.database import init_db, get_prospects, get_prospects_due_today, add_prospect
    from src.agents.outreach_agent import run_daily_outreach, seed_prospects
    init_db()

    # ── Top actions ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(f"🚀 {_t('outreach_run')}", type="primary", use_container_width=True):
            with st.spinner("Enviando emails personalizados..." if not is_en else "Sending personalized emails..."):
                result = run_daily_outreach(daily_limit=20)
            st.success(f"✅ {result['sent']} emails enviados | {result['failed']} falhas")
            if result["contacts"]:
                for c in result["contacts"]:
                    st.write(f"  → {c['company']} ({c['email']})")
    with col2:
        if st.button(f"🧪 {_t('outreach_dry')}", use_container_width=True):
            with st.spinner("Simulando..." if not is_en else "Simulating..."):
                result = run_daily_outreach(daily_limit=20, dry_run=True)
            st.info(f"Simulação: {result['sent']} emails seriam enviados")
            for c in result["contacts"]:
                st.write(f"  → {c['company']} — {c.get('subject','')}")
    with col3:
        if st.button(f"📋 {_t('outreach_seed')}", use_container_width=True):
            n = seed_prospects()
            st.success(f"{n} prospects carregados na base")

    st.markdown("---")

    # ── Pipeline de prospects ─────────────────────────────────────────────────
    all_prospects = get_prospects(limit=200)
    pending   = [p for p in all_prospects if p["status"] == "pending" and p["email"]]
    contacted = [p for p in all_prospects if p["status"] == "contacted"]
    no_email  = [p for p in all_prospects if not p["email"]]

    m1, m2, m3 = st.columns(3)
    m1.metric(_t("outreach_pending"),   len(pending))
    m2.metric(_t("outreach_contacted"), len(contacted))
    m3.metric(_t("outreach_no_email"),  len(no_email))

    # ── Pending table ─────────────────────────────────────────────────────────
    if pending:
        st.subheader(f"📋 {_t('outreach_pending')} ({len(pending)})")
        rows = []
        for p in pending:
            rows.append({
                "Empresa": p["company_name"],
                "Email": p["email"],
                "Contato": p["contact_role"],
                "Segmento": p["segment"],
                "Prioridade": p["priority"],
            })
        import pandas as _pd
        st.dataframe(_pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Contacted table ───────────────────────────────────────────────────────
    if contacted:
        st.subheader(f"✅ {_t('outreach_contacted')} ({len(contacted)})")
        rows = []
        for p in contacted:
            rows.append({
                "Empresa": p["company_name"],
                "Email": p["email"],
                "Emails Enviados": p["emails_sent"],
                "Último Contato": (p["last_contact"] or "")[:10],
            })
        st.dataframe(_pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── No email ──────────────────────────────────────────────────────────────
    if no_email:
        with st.expander(f"⚠️ {_t('outreach_no_email')} — {len(no_email)} empresas"):
            for p in no_email:
                st.write(f"**{p['company_name']}** — {p['contact_role']} — {p['segment']}")

    # ── Add new prospect ──────────────────────────────────────────────────────
    with st.expander("➕ Adicionar novo prospect"):
        with st.form("add_prospect_form"):
            c1, c2 = st.columns(2)
            company  = c1.text_input("Empresa")
            email    = c2.text_input("Email")
            phone    = c1.text_input("Telefone")
            role     = c2.text_input("Cargo alvo")
            segment  = st.text_input("Segmento")
            desc     = st.text_area("Descrição", height=80)
            is_part  = st.checkbox("Parceiro estratégico (não cliente)")
            priority = st.selectbox("Prioridade", ["high", "medium", "low"])
            if st.form_submit_button("Adicionar"):
                if company and email:
                    add_prospect(company_name=company, email=email, phone=phone,
                                 contact_role=role, segment=segment, description=desc,
                                 is_partner=is_part, priority=priority)
                    st.success(f"{company} adicionado!")
                    st.rerun()
                else:
                    st.error("Empresa e email são obrigatórios.")


# ===========================================================================
# Admin Director Page
# ===========================================================================

def _page_admin_director(_year: int = 2025) -> None:
    """Admin-only Sales Director command center."""
    lang = st.session_state.get("lang", "PT")

    st.markdown(f"""
    <h1 style="color:#4DB6AC; margin-bottom:0.25rem;">
      {"Diretora IA — Centro de Comando" if lang == "PT" else "AI Director — Command Center"}
    </h1>
    <p style="color:#8899AA; font-size:0.9rem; margin-bottom:1.5rem;">
      {"Sprint de 22 dias · Meta R$50.000 até 30 de abril de 2026" if lang == "PT" else "22-day sprint · Goal R$50,000 by April 30, 2026"}
    </p>
    """, unsafe_allow_html=True)

    # Load lead manager
    try:
        from src.crm.lead_manager import LeadManager
        lm = LeadManager()
        stats = lm.get_pipeline_stats()
        progress = lm.get_days_to_goal()
    except Exception as exc:
        st.error(f"LeadManager error: {exc}")
        return

    # -----------------------------------------------------------------------
    # Goal progress bar
    # -----------------------------------------------------------------------
    revenue = progress.get("revenue", 0)
    goal = progress.get("goal", 50000)
    pct = progress.get("pct", 0)
    remaining = progress.get("remaining", goal)
    days_left = progress.get("days_remaining", 22)

    bar_color = "#4DB6AC" if pct >= 60 else ("#f0a500" if pct >= 20 else "#e53935")
    goal_label = "Meta" if lang == "PT" else "Goal"
    st.markdown(f"""
    <div style="background:#112240; border:1px solid #1E3A5F; border-radius:10px; padding:1rem 1.5rem; margin-bottom:1.5rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
        <span style="color:#E8EDF5; font-weight:600;">{goal_label}: R${revenue:,.0f} / R${goal:,.0f}</span>
        <span style="color:{bar_color}; font-weight:700; font-size:1.1rem;">{pct:.1f}%</span>
      </div>
      <div style="background:#0A1628; border-radius:6px; height:12px; overflow:hidden;">
        <div style="background:{bar_color}; width:{min(pct,100):.1f}%; height:100%; border-radius:6px;
                    transition:width 0.5s ease;"></div>
      </div>
      <div style="color:#8899AA; font-size:0.78rem; margin-top:0.4rem;">
        {"Faltam" if lang == "PT" else "Remaining"} R${remaining:,.0f} · {days_left} {"dias" if lang == "PT" else "days"}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # 4 KPI cards
    # -----------------------------------------------------------------------
    total_leads = stats.get("total", 0)
    hot_leads = stats.get("hot", 0)

    kc1, kc2, kc3, kc4 = st.columns(4)
    kpi_style = 'style="background:#112240;border:1px solid #1E3A5F;border-radius:10px;padding:1rem;text-align:center;"'
    with kc1:
        st.markdown(f'<div {kpi_style}><p style="color:#8899AA;font-size:0.75rem;margin:0;">{"Leads Totais" if lang == "PT" else "Total Leads"}</p><h2 style="color:#4DB6AC;margin:0.25rem 0 0;">{total_leads}</h2></div>', unsafe_allow_html=True)
    with kc2:
        st.markdown(f'<div {kpi_style}><p style="color:#8899AA;font-size:0.75rem;margin:0;">{"Leads Quentes" if lang == "PT" else "Hot Leads"}</p><h2 style="color:#FF6B6B;margin:0.25rem 0 0;">{hot_leads}</h2></div>', unsafe_allow_html=True)
    with kc3:
        st.markdown(f'<div {kpi_style}><p style="color:#8899AA;font-size:0.75rem;margin:0;">{"Receita Acumulada" if lang == "PT" else "Revenue"}</p><h2 style="color:#4DB6AC;margin:0.25rem 0 0;">R${revenue:,.0f}</h2></div>', unsafe_allow_html=True)
    with kc4:
        dl_color = "#e53935" if days_left <= 5 else ("#f0a500" if days_left <= 10 else "#4DB6AC")
        st.markdown(f'<div {kpi_style}><p style="color:#8899AA;font-size:0.75rem;margin:0;">{"Dias Restantes" if lang == "PT" else "Days Left"}</p><h2 style="color:{dl_color};margin:0.25rem 0 0;">{days_left}</h2></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Pipeline visual
    # -----------------------------------------------------------------------
    st.markdown(f"### {'Pipeline de Vendas' if lang == 'PT' else 'Sales Pipeline'}")
    by_status = stats.get("by_status", {})
    pipe_cols = st.columns(4)
    pipe_stages = [
        ("new",        "Novos" if lang == "PT" else "New",            "#8899AA"),
        ("demo_tested","Demo Testado" if lang == "PT" else "Demo'd",  "#f0a500"),
        ("contacted",  "Contatado" if lang == "PT" else "Contacted",  "#4DB6AC"),
        ("subscribed", "Assinante" if lang == "PT" else "Subscriber", "#66BB6A"),
    ]
    for col, (status_key, label, color) in zip(pipe_cols, pipe_stages):
        count = by_status.get(status_key, 0)
        with col:
            st.markdown(f"""
            <div style="background:#112240;border:1px solid #1E3A5F;border-radius:10px;
                        padding:1rem;text-align:center;">
              <p style="color:{color};font-size:0.8rem;font-weight:600;margin:0;">{label}</p>
              <h3 style="color:#E8EDF5;margin:0.3rem 0 0;font-size:2rem;">{count}</h3>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Hot leads table
    # -----------------------------------------------------------------------
    st.markdown(f"### {'Leads Quentes — Prioridade de Contato' if lang == 'PT' else 'Hot Leads — Contact Priority'}")
    try:
        hot = lm.get_hot_leads()
        if not hot:
            st.info("Nenhum lead quente ainda." if lang == "PT" else "No hot leads yet.")
        else:
            for lead in hot[:10]:
                temp_color = "#FF6B6B" if lead.temperature == "hot" else "#f0a500"
                temp_label = "HOT" if lead.temperature == "hot" else "WARM"
                with st.container():
                    col_info, col_act1, col_act2 = st.columns([5, 1.5, 1.5])
                    with col_info:
                        st.markdown(f"""
                        <div style="background:#112240;border:1px solid #1E3A5F;border-radius:8px;padding:0.75rem 1rem;">
                          <span style="background:{temp_color};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:700;">{temp_label}</span>
                          <span style="color:#E8EDF5;margin-left:0.75rem;font-weight:600;">{lead.email}</span>
                          <span style="color:#8899AA;font-size:0.8rem;margin-left:0.5rem;">· {lead.questions_asked} {"perguntas" if lang == "PT" else "questions"} · {lead.lang}</span>
                          {f'<span style="color:#4DB6AC;font-size:0.75rem;margin-left:0.5rem;">{lead.country_hint}</span>' if lead.country_hint else ''}
                          <br><span style="color:#8899AA;font-size:0.72rem;">{lead.timestamp[:10] if lead.timestamp else "—"}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_act1:
                        btn_label = "Contatado" if lang == "PT" else "Contacted"
                        if st.button(btn_label, key=f"contact_{lead.email}", use_container_width=True):
                            lm.mark_contacted(lead.email)
                            st.success(f"{lead.email} {'marcado como contatado' if lang == 'PT' else 'marked as contacted'}")
                            st.rerun()
                    with col_act2:
                        msg_label = "Mensagem" if lang == "PT" else "Message"
                        if st.button(msg_label, key=f"msg_{lead.email}", use_container_width=True):
                            st.session_state[f"show_draft_{lead.email}"] = True
                    # Show draft if requested
                    if st.session_state.get(f"show_draft_{lead.email}"):
                        from src.agents.director_agent import _tool_draft_whatsapp
                        draft = _tool_draft_whatsapp(lead.email, lead.lang)
                        st.code(draft, language=None)
    except Exception as exc:
        st.error(f"Hot leads error: {exc}")

    st.markdown("<br>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Email sequences
    # -----------------------------------------------------------------------
    st.markdown(f"### {'Sequências de Email' if lang == 'PT' else 'Email Sequences'}")
    run_label = "Executar Sequências de Email" if lang == "PT" else "Run Email Sequences"
    if st.button(run_label, type="primary", use_container_width=False):
        with st.spinner("Processando..." if lang == "PT" else "Processing..."):
            try:
                from src.crm.email_sequencer import EmailSequencer
                seq = EmailSequencer()
                result = seq.run_sequences()
                st.success(
                    f"{'Enviados' if lang == 'PT' else 'Sent'}: {result['sent']} · "
                    f"{'Ignorados' if lang == 'PT' else 'Skipped'}: {result['skipped']} · "
                    f"Erros: {result['errors']}"
                )
                if result.get("detail"):
                    with st.expander("Detalhes" if lang == "PT" else "Details"):
                        st.json(result["detail"])
            except Exception as exc:
                st.error(f"Sequencer error: {exc}")

    st.markdown("<br>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Director AI Chat
    # -----------------------------------------------------------------------
    st.markdown(f"### {'Chat com a Diretora IA' if lang == 'PT' else 'Chat with AI Director'}")

    if "director_history" not in st.session_state:
        st.session_state["director_history"] = []

    # Always reinitialize if not online (picks up newly added API keys)
    def _init_director():
        try:
            from src.agents.director_agent import DirectorAgent
            agent = DirectorAgent()
            st.session_state["director_agent"] = agent
            return agent
        except Exception as exc:
            st.error(f"DirectorAgent init error: {exc}")
            st.session_state["director_agent"] = None
            return None

    agent_d = st.session_state.get("director_agent")
    if agent_d is None or not getattr(agent_d, "is_online", False):
        agent_d = _init_director()

    # Manual reinit button
    col_r, col_d = st.columns([1, 2])
    with col_r:
        if st.button("🔄 Reiniciar Diretora IA", type="secondary"):
            st.session_state.pop("director_agent", None)
            st.session_state.pop("director_history", None)
            st.rerun()
    with col_d:
        import os as _os
        ant_key = bool(_os.getenv("ANTHROPIC_API_KEY", ""))
        groq_key_d = bool(_os.getenv("GROQ_API_KEY", ""))
        online = getattr(agent_d, "is_online", False)
        st.caption(
            f"Anthropic: {'✅' if ant_key else '❌'} | "
            f"Groq: {'✅' if groq_key_d else '❌'} | "
            f"Online: {'✅' if online else '❌'}"
        )

    # Daily brief button
    brief_label = "Briefing Diário" if lang == "PT" else "Daily Briefing"
    if st.button(brief_label, type="secondary"):
        if agent_d:
            with st.spinner("Gerando briefing..." if lang == "PT" else "Generating briefing..."):
                brief = agent_d.get_daily_brief(lang=lang)
            st.session_state["director_history"].append({"role": "assistant", "content": brief})
            st.rerun()

    # Suggestion chips
    suggestions = TRANSLATIONS[lang].get("director_suggestions", [])
    sug_cols = st.columns(len(suggestions))
    for col, sug in zip(sug_cols, suggestions):
        if col.button(sug[:35] + "…" if len(sug) > 35 else sug, key=f"dsug_{sug[:20]}"):
            st.session_state["director_pending"] = sug

    # Chat history
    st.markdown("---")
    for msg in st.session_state["director_history"]:
        if msg["role"] == "user":
            st.markdown(f'<div style="background:#1E3A5F;border-radius:8px;padding:0.75rem 1rem;margin:0.5rem 0;"><b style="color:#4DB6AC;">{"Você" if lang == "PT" else "You"}:</b> {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="background:#112240;border:1px solid #1E3A5F;border-radius:8px;padding:0.75rem 1rem;margin:0.5rem 0;">{msg["content"]}</div>', unsafe_allow_html=True)

    # Input
    placeholder = "Faça uma pergunta para a Diretora IA..." if lang == "PT" else "Ask the AI Director..."
    user_input = st.chat_input(placeholder)
    if "director_pending" in st.session_state:
        user_input = st.session_state.pop("director_pending")

    if user_input and agent_d:
        st.session_state["director_history"].append({"role": "user", "content": user_input})
        with st.spinner("Diretora analisando..." if lang == "PT" else "Director analyzing..."):
            resp = agent_d.chat(user_input, lang=lang)
        # ── Quality Control audit ────────────────────────────────────────────
        try:
            from src.quality.ai_auditor import AIOutputAuditor
            from src.db.database import log_quality_check
            auditor = AIOutputAuditor()
            audit_r = auditor.audit(resp, tool_calls_made=[], module="director_ai", lang=lang)
            log_quality_check(
                module="director_ai",
                check_type="ai_output_audit",
                result=audit_r.result_str,
                error_level=audit_r.risk_level,
                details=audit_r.to_details_json(),
                blocked=audit_r.blocked,
            )
            resp = audit_r.audited_text
        except Exception:
            pass
        st.session_state["director_history"].append({"role": "assistant", "content": resp})
        st.rerun()

    if st.session_state["director_history"]:
        clear_label = "Limpar conversa" if lang == "PT" else "Clear conversation"
        if st.button(clear_label, type="secondary"):
            st.session_state["director_history"] = []
            if agent_d:
                agent_d.reset()
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # All leads raw table
    # -----------------------------------------------------------------------
    with st.expander(f"{'Todos os Leads' if lang == 'PT' else 'All Leads'} ({total_leads})"):
        all_leads = lm.get_all_leads()
        if all_leads:
            rows = []
            for lead in all_leads:
                rows.append({
                    "Email": lead.email,
                    "Status": lead.status,
                    "Temp": lead.temperature,
                    "Q": lead.questions_asked,
                    "Lang": lead.lang,
                    "Country": lead.country_hint,
                    "Last Contact": lead.last_contact or "—",
                    "Follow-ups": lead.follow_up_count,
                    "Captured": lead.timestamp[:10] if lead.timestamp else "—",
                })
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum lead capturado ainda." if lang == "PT" else "No leads captured yet.")


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
        _is_admin = (
            st.session_state.get("auth_user") == _APP_USERNAME
            or st.session_state.get("is_admin")
        )
        nav_keys_active = _NAV_KEYS + (["outreach", "director", "quality", "costs"] if _is_admin else [])
        nav_t_keys_active = _NAV_T_KEYS + (["nav_outreach", "nav_director", "nav_quality", "nav_costs"] if _is_admin else [])
        nav_labels = [_t(k) for k in nav_t_keys_active]
        # Preserve current page across language switches using internal key
        current_key = st.session_state.get("page_key", "overview")
        current_idx = nav_keys_active.index(current_key) if current_key in nav_keys_active else 0
        selected_idx = st.radio(
            "nav",
            options=range(len(nav_keys_active)),
            format_func=lambda i: nav_labels[i],
            index=current_idx,
            label_visibility="collapsed",
        )
        page_key = nav_keys_active[selected_idx]
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
# Finance Manager Page
# ===========================================================================

def _page_finance_manager() -> None:
    """Gerente Financeiro — ROI, custos e investimentos da plataforma."""
    lang  = st.session_state.get("lang", "PT")
    is_en = lang == "EN"

    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #0A1628; }
    .fin-card {
        background: #112240; border: 1px solid #1E3A5F; border-radius: 12px;
        padding: 1.25rem 1.5rem; margin-bottom: 1rem;
    }
    .fin-metric { color: #4DB6AC; font-size: 1.8rem; font-weight: 700; }
    .fin-label  { color: #8899AA; font-size: 0.8rem; margin-bottom: 0.25rem; }
    .fin-sub    { color: #B0BEC5; font-size: 0.82rem; margin-top: 0.25rem; }
    .fin-ok     { color: #4DB6AC; font-weight: 600; }
    .fin-warn   { color: #f0a500; font-weight: 600; }
    .fin-bad    { color: #e53935; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

    title = "Finance Manager — ROI & Cost Report" if is_en else "Gerente Financeiro — ROI & Custos"
    st.markdown(f"<h2 style='color:#4DB6AC; margin-bottom:0.25rem;'>💰 {title}</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:#8899AA; font-size:0.85rem;'>{'Real platform costs + AI usage + ROI analysis' if is_en else 'Custos reais da plataforma + uso de IA + análise de retorno'}</p>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Load AI token usage ──────────────────────────────────────────────────
    try:
        from src.agents.pharma_agent import _load_budget
        budget = _load_budget()
        ai_cost_usd   = budget.get("cost_usd", 0.0)
        tokens_in     = budget.get("tokens_input", 0)
        tokens_out    = budget.get("tokens_output", 0)
        budget_month  = budget.get("month", "N/A")
    except Exception:
        ai_cost_usd, tokens_in, tokens_out, budget_month = 0.0, 0, 0, "N/A"

    # ── Fixed monthly costs (USD) ────────────────────────────────────────────
    COSTS = {
        "Render (hosting)":        7.00,
        "Domain (pharmaceuticaai)": 0.83,   # ~$10/year
        "Groq API":                 0.00,   # free tier
        "DeepSeek V3":              0.50,   # estimate
        "Stripe fees (% revenue)":  0.00,   # only on sales
    }
    fixed_usd = sum(COSTS.values())
    total_monthly_usd = fixed_usd + ai_cost_usd

    # ── Revenue (from DB) ────────────────────────────────────────────────────
    try:
        from src.agents.pharma_agent import _get_monthly_revenue_usd
        revenue_usd = _get_monthly_revenue_usd()
    except Exception:
        revenue_usd = 0.0

    # ── Total invested (manual estimate) ────────────────────────────────────
    # Claude Pro plan + development time value
    claude_monthly = 110.0  # BRL → USD ~$20
    total_invested_usd = 20.0 + 7.0 * 3  # 3 months Render + Claude

    brl_rate = 5.70
    total_monthly_brl = total_monthly_usd * brl_rate
    revenue_brl       = revenue_usd * brl_rate

    roi_pct = ((revenue_usd - total_monthly_usd) / total_monthly_usd * 100) if total_monthly_usd > 0 else 0.0
    breakeven_clients = max(1, int(total_monthly_usd / 299) + 1)  # Starter plan USD

    # ── KPI Cards ───────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="fin-card">
          <div class="fin-label">{'Monthly Cost' if is_en else 'Custo Mensal'}</div>
          <div class="fin-metric">US$ {total_monthly_usd:.2f}</div>
          <div class="fin-sub">R$ {total_monthly_brl:.0f}/mês</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        rev_color = "fin-ok" if revenue_usd > 0 else "fin-warn"
        st.markdown(f"""
        <div class="fin-card">
          <div class="fin-label">{'Monthly Revenue' if is_en else 'Receita Mensal'}</div>
          <div class="fin-metric">US$ {revenue_usd:.0f}</div>
          <div class="fin-sub"><span class="{rev_color}">R$ {revenue_brl:.0f}/mês</span></div>
        </div>""", unsafe_allow_html=True)
    with c3:
        roi_color = "fin-ok" if roi_pct > 0 else ("fin-warn" if roi_pct > -50 else "fin-bad")
        st.markdown(f"""
        <div class="fin-card">
          <div class="fin-label">ROI</div>
          <div class="fin-metric"><span class="{roi_color}">{roi_pct:+.0f}%</span></div>
          <div class="fin-sub">{'vs monthly cost' if is_en else 'vs custo mensal'}</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="fin-card">
          <div class="fin-label">{'Break-even' if is_en else 'Ponto de Equilíbrio'}</div>
          <div class="fin-metric">{breakeven_clients}</div>
          <div class="fin-sub">{'Starter clients needed' if is_en else 'clientes Starter necessários'}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Cost Breakdown ───────────────────────────────────────────────────────
    col_costs, col_ai = st.columns(2)

    with col_costs:
        st.markdown(f"<h4 style='color:#E2EAF4;'>{'Infrastructure Costs' if is_en else 'Custos de Infraestrutura'} — {budget_month}</h4>", unsafe_allow_html=True)
        for item, val in COSTS.items():
            color = "fin-ok" if val == 0 else "fin-label"
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; padding:0.5rem 0; border-bottom:1px solid #1E3A5F;">
              <span style="color:#B0BEC5; font-size:0.85rem;">{item}</span>
              <span class="{color}" style="font-size:0.85rem; font-weight:600;">
                {'FREE' if val == 0 else f'US$ {val:.2f}'}
              </span>
            </div>""", unsafe_allow_html=True)
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; padding:0.75rem 0; margin-top:0.5rem;">
          <span style="color:#E2EAF4; font-weight:700;">{'AI API Usage' if is_en else 'Uso de IA (tokens)'}</span>
          <span style="color:#4DB6AC; font-weight:700;">US$ {ai_cost_usd:.4f}</span>
        </div>
        <div style="display:flex; justify-content:space-between; padding:0.5rem 0; border-top:2px solid #4DB6AC; margin-top:0.25rem;">
          <span style="color:#E2EAF4; font-weight:700; font-size:1rem;">TOTAL</span>
          <span style="color:#4DB6AC; font-weight:700; font-size:1rem;">US$ {total_monthly_usd:.2f}</span>
        </div>""", unsafe_allow_html=True)

    with col_ai:
        st.markdown(f"<h4 style='color:#E2EAF4;'>{'AI Token Usage' if is_en else 'Uso de Tokens de IA'} — {budget_month}</h4>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class="fin-card">
          <div style="display:flex; justify-content:space-between; margin-bottom:0.75rem;">
            <span style="color:#8899AA;">{'Input tokens' if is_en else 'Tokens entrada'}</span>
            <span style="color:#E2EAF4; font-weight:600;">{tokens_in:,}</span>
          </div>
          <div style="display:flex; justify-content:space-between; margin-bottom:0.75rem;">
            <span style="color:#8899AA;">{'Output tokens' if is_en else 'Tokens saída'}</span>
            <span style="color:#E2EAF4; font-weight:600;">{tokens_out:,}</span>
          </div>
          <div style="display:flex; justify-content:space-between; margin-bottom:0.75rem;">
            <span style="color:#8899AA;">{'Total tokens' if is_en else 'Total tokens'}</span>
            <span style="color:#E2EAF4; font-weight:600;">{tokens_in + tokens_out:,}</span>
          </div>
          <div style="display:flex; justify-content:space-between; border-top:1px solid #1E3A5F; padding-top:0.75rem;">
            <span style="color:#8899AA;">{'AI cost this month' if is_en else 'Custo IA este mês'}</span>
            <span style="color:#4DB6AC; font-weight:700;">US$ {ai_cost_usd:.4f}</span>
          </div>
        </div>
        <div style="background:#0A1628; border:1px solid #00897B; border-radius:8px; padding:0.75rem 1rem; margin-top:0.5rem;">
          <p style="color:#4DB6AC; font-weight:600; margin:0 0 0.25rem; font-size:0.85rem;">
            {'💡 Cost structure' if is_en else '💡 Estrutura de custos'}
          </p>
          <p style="color:#B0BEC5; font-size:0.8rem; margin:0; line-height:1.6;">
            {'Groq (free) → DeepSeek (~US$0.001/query) → Claude (paid)' if is_en else 'Groq (grátis) → DeepSeek (~US$0,001/consulta) → Claude (pago)'}
          </p>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── ROI Projection ───────────────────────────────────────────────────────
    st.markdown(f"<h4 style='color:#E2EAF4;'>{'Revenue Projection' if is_en else 'Projeção de Receita'}</h4>", unsafe_allow_html=True)
    scenarios = [
        (1, 299, "1 Starter", "fin-warn"),
        (3, 299, "3 Starter", "fin-ok"),
        (1, 499, "1 Pro", "fin-ok"),
        (5, 299, "5 Starter", "fin-ok"),
        (1, 1499, "1 Enterprise", "fin-ok"),
        (10, 299, "10 Starter", "fin-ok"),
    ]
    cols = st.columns(len(scenarios))
    for col, (n, price, label, color) in zip(cols, scenarios):
        rev = n * price
        profit = rev - total_monthly_usd
        with col:
            st.markdown(f"""
            <div class="fin-card" style="text-align:center; padding:0.75rem;">
              <div style="color:#8899AA; font-size:0.72rem;">{label}</div>
              <div class="{color}" style="font-size:1.1rem; font-weight:700; margin:0.25rem 0;">US$ {rev:,}</div>
              <div style="color:#B0BEC5; font-size:0.7rem;">{'profit' if is_en else 'lucro'}: <span class="{'fin-ok' if profit > 0 else 'fin-bad'}">US$ {profit:+,.0f}</span></div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Investment Summary ───────────────────────────────────────────────────
    st.markdown(f"<h4 style='color:#E2EAF4;'>{'Total Investment to Date' if is_en else 'Investimento Total até Hoje'}</h4>", unsafe_allow_html=True)
    investments = [
        ("Claude Pro (desenvolvimento)", "R$ 110/mês", "Custo de desenvolvimento com IA"),
        ("Render (3 meses)", f"US$ {7*3:.0f}", "Hospedagem da plataforma"),
        ("Domínio pharmaceuticaai.com", "~US$ 10/ano", "Identidade online"),
        ("Groq / DeepSeek / APIs", "~US$ 5", "Tokens de IA"),
        ("Tempo de desenvolvimento", "Inestimável", "Valor do produto construído"),
    ]
    for item, val, desc in investments:
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; align-items:center;
                    padding:0.6rem 1rem; background:#112240; border-radius:8px; margin-bottom:0.4rem;">
          <div>
            <div style="color:#E2EAF4; font-size:0.85rem; font-weight:600;">{item}</div>
            <div style="color:#8899AA; font-size:0.75rem;">{desc}</div>
          </div>
          <div style="color:#4DB6AC; font-weight:700; font-size:0.9rem;">{val}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:#0A1628; border:2px solid #4DB6AC; border-radius:12px;
                padding:1.25rem 1.5rem; margin-top:1rem; text-align:center;">
      <p style="color:#8899AA; font-size:0.8rem; margin:0 0 0.5rem;">
        {'Bottom line' if is_en else 'Conclusão'}
      </p>
      <p style="color:#E2EAF4; font-size:1rem; font-weight:600; margin:0; line-height:1.6;">
        {'1 client at US$299/month covers ALL platform costs. Everything above that is profit.' if is_en else
         '1 cliente no plano Starter (US$299/mês) cobre TODOS os custos da plataforma. Tudo acima disso é lucro.'}
      </p>
    </div>
    """, unsafe_allow_html=True)


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
        "outreach":   _page_outreach,
        "director":   _page_admin_director,
        "quality":    _page_quality,
        "costs":      _page_finance_manager,
    }

    fn = pages.get(page_key)
    if fn:
        # these admin pages don't use `year`
        if page_key in ("director", "outreach", "quality", "costs"):
            fn()
        else:
            fn(year)


if __name__ == "__main__":
    main()
