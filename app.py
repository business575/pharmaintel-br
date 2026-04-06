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
# Page config — MUST be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="PharmaIntel BR",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
_APP_USERNAME      = _secret("APP_USERNAME", "admin")
_APP_PASSWORD      = _secret("APP_PASSWORD", "pharmaintel2024")
_APP_PASSWORD_HASH = _secret("APP_PASSWORD_HASH", "")


def _check_password(username: str, password: str) -> bool:
    """Verify credentials using constant-time comparison (timing-safe)."""
    user_ok = hmac.compare_digest(username.strip(), _APP_USERNAME)
    if _APP_PASSWORD_HASH:
        # Compare against sha256 hash stored in env
        entered_hash = hashlib.sha256(password.encode()).hexdigest()
        pass_ok = hmac.compare_digest(entered_hash, _APP_PASSWORD_HASH)
    else:
        # Plaintext comparison (dev mode)
        pass_ok = hmac.compare_digest(password, _APP_PASSWORD)
    return user_ok and pass_ok


def _login_page() -> None:
    """Render login form and block the app until authenticated."""
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background: #0A1628; }
    [data-testid="stSidebar"] { display: none; }
    </style>
    """, unsafe_allow_html=True)

    col_l, col_m, col_r = st.columns([1, 1.4, 1])
    with col_m:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align:center; margin-bottom:2rem;">
          <span style="font-size:3rem;">💊</span>
          <h1 style="color:#4DB6AC; font-size:1.8rem; margin:0.5rem 0 0.25rem;">PharmaIntel BR</h1>
          <p style="color:#8899AA; font-size:0.9rem;">Inteligência de Mercado Farmacêutico</p>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Usuário", placeholder="admin")
            password = st.text_input("Senha", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")

            if submitted:
                if _check_password(username, password):
                    st.session_state["authenticated"] = True
                    st.session_state["auth_user"] = username
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.", icon="🔒")

        st.markdown("""
        <p style="text-align:center; color:#8899AA; font-size:0.75rem; margin-top:1.5rem;">
          Configure credenciais em <code>.env</code> via APP_USERNAME / APP_PASSWORD
        </p>
        """, unsafe_allow_html=True)
    st.stop()


# Gate: show login page if not authenticated
if not st.session_state.get("authenticated", False):
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
      <p>Inteligência de Mercado Farmacêutico Brasileiro &nbsp;·&nbsp; {page}</p>
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
    st.info(
        "**Modo demonstração** — Exibindo dados simulados. "
        "Execute o ETL na aba **Pipeline ETL** para carregar dados reais.",
        icon="ℹ️",
    )


# ===========================================================================
# Pages
# ===========================================================================

def page_overview(year: int) -> None:
    render_header("Visão Geral")

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
        ("Total FOB", fmt_usd(total_fob), f"Capítulo 30 · {year}"),
        ("Total FOB (BRL)", fmt_brl(total_fob * 5.10), "USD × R$5,10"),
        ("Volume", f"{total_kg/1e6:.1f}M kg", "Peso líquido"),
        ("NCMs Distintos", f"{n_ncms}", "Capítulo 30"),
        ("Países Origem", f"{n_paises}", "Fornecedores ativos"),
    ]
    for col, (label, value, sub) in zip(cols, kpis):
        col.markdown(kpi_card(label, value, sub), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts row 1 ────────────────────────────────────────────────────────
    c1, c2 = st.columns([3, 2])

    with c1:
        st.markdown('<div class="section-title">Evolução Mensal das Importações (FOB)</div>', unsafe_allow_html=True)
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
                mode="lines+markers", name="Tendência",
                line=dict(color=COLOR_ACCENT, width=2),
                marker=dict(size=6, color=COLOR_ACCENT),
            ))
            apply_theme(fig, f"Importações Mensais {year} (US$ Milhões)")
            fig.update_yaxes(title_text="USD Milhões")
            st.plotly_chart(fig, width="stretch")

    with c2:
        st.markdown('<div class="section-title">Top 8 Países de Origem</div>', unsafe_allow_html=True)
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
    render_header("Importações — Capítulo 30")

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
    render_header("ANVISA — Registros")

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
    render_header("UN Comtrade — Contexto Global")

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
    render_header("Empresas — Detentores de Registro ANVISA")

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
    render_header("Pipeline ETL — 5 Estágios")

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
        run_year = st.selectbox("Ano", [2024, 2023, 2022], index=0)
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
    render_header("Agente IA — PharmaIntel AI")

    # Initialize session state
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "agent" not in st.session_state:
        try:
            from src.agents.pharma_agent import create_agent
            st.session_state.agent = create_agent(year=year)
        except Exception as exc:
            st.error(f"Erro ao inicializar agente: {exc}")
            return

    agent = st.session_state.agent

    # Status
    if agent.is_available:
        st.markdown('<span class="badge-ok">Agente ATIVO — Groq/Llama 3.3 70B</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge-warn">Modo Fallback — Configure GROQ_API_KEY</span>', unsafe_allow_html=True)
        st.info("Obtenha uma chave gratuita em https://console.groq.com e adicione ao arquivo `.env`")

    st.markdown("<br>", unsafe_allow_html=True)

    # Suggestion chips
    suggestions = [
        "Quais são os 5 NCMs com maior valor FOB?",
        "Mostre a tendência mensal das importações",
        "Quais países lideram as importações?",
        "Existe algum alerta de compliance ANVISA?",
        "Qual o preço médio por kg dos principais NCMs?",
    ]
    st.markdown("**Sugestões:**")
    cols = st.columns(len(suggestions))
    for col, sug in zip(cols, suggestions):
        if col.button(sug[:30] + "…" if len(sug) > 30 else sug, width="stretch"):
            st.session_state.pending_message = sug

    # Chat history
    st.markdown("---")
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-user">**Você:** {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-ai">{msg["content"]}</div>', unsafe_allow_html=True)

    # Input
    user_input = st.chat_input("Faça uma pergunta sobre o mercado farmacêutico...")

    # Handle suggestion button clicks
    if "pending_message" in st.session_state:
        user_input = st.session_state.pop("pending_message")

    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.spinner("PharmaIntel AI está analisando..."):
            response = agent.chat(user_input)
        st.session_state.chat_history.append({"role": "assistant", "content": response.text})
        if response.tool_calls_made:
            st.caption(f"Ferramentas utilizadas: {', '.join(response.tool_calls_made)} · Tokens: {response.tokens_used:,}")
        st.rerun()

    # Reset button
    if st.session_state.chat_history:
        if st.button("Limpar conversa", type="secondary"):
            st.session_state.chat_history = []
            agent.reset()
            st.rerun()


# ===========================================================================
# Sidebar & Navigation
# ===========================================================================

def sidebar() -> tuple[str, int]:
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center; padding: 1rem 0 0.5rem;">
          <span style="font-size:2rem;">💊</span>
          <h2 style="color:#4DB6AC; margin:0.25rem 0 0; font-size:1.2rem;">PharmaIntel BR</h2>
          <p style="color:#8899AA; font-size:0.75rem; margin:0;">v2.0 — Mercado Farmacêutico</p>
        </div>
        <hr style="border-color:#1E3A5F; margin:0.75rem 0;">
        """, unsafe_allow_html=True)

        page = st.radio(
            "Navegação",
            ["Visão Geral", "Importações", "ANVISA", "Empresas", "UN Comtrade", "Pipeline ETL", "Agente IA"],
            label_visibility="collapsed",
        )

        st.markdown("<hr style='border-color:#1E3A5F;'>", unsafe_allow_html=True)
        year = st.selectbox("Ano de referência", [2024, 2023, 2022], index=0)

        # Data status
        st.markdown('<p style="color:#8899AA; font-size:0.75rem; margin:0.5rem 0 0.25rem;">STATUS DOS DADOS</p>', unsafe_allow_html=True)
        data_files = {
            "Importações": f"pharma_imports_{year}.parquet",
            "KPIs":        f"kpis_anuais_{year}.parquet",
            "Empresas":    "empresas_anvisa.parquet",
            "Comtrade":    f"comtrade_{year}.parquet",
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
        st.markdown('<p style="color:#8899AA; font-size:0.75rem; margin:0.25rem 0;">API KEYS</p>', unsafe_allow_html=True)
        st.markdown(f'<span class="{"badge-ok" if groq_key else "badge-warn"}">Groq: {"OK" if groq_key else "Missing"}</span><br>', unsafe_allow_html=True)
        st.markdown(f'<span class="{"badge-ok" if ctrade_key else "badge-warn"}">Comtrade: {"OK" if ctrade_key else "Missing"}</span>', unsafe_allow_html=True)

        # Logout
        st.markdown("<hr style='border-color:#1E3A5F; margin:1rem 0 0.5rem;'>", unsafe_allow_html=True)
        auth_user = st.session_state.get("auth_user", _APP_USERNAME)
        st.markdown(f'<p style="color:#8899AA; font-size:0.75rem; margin:0 0 0.4rem;">Logado como <b style="color:#4DB6AC;">{auth_user}</b></p>', unsafe_allow_html=True)
        if st.button("Sair", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state["auth_user"] = ""
            st.rerun()

    return page, year


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    page, year = sidebar()

    pages = {
        "Visão Geral":  page_overview,
        "Importações":  page_importacoes,
        "ANVISA":       page_anvisa,
        "Empresas":     page_empresas,
        "UN Comtrade":  page_comtrade,
        "Pipeline ETL": page_etl,
        "Agente IA":    page_agent,
    }

    fn = pages.get(page)
    if fn:
        fn(year)


if __name__ == "__main__":
    main()
