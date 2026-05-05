"""
report_generator.py — PharmaIntel BR PDF Report Generator
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT      = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"

DARK   = (10, 22, 40)
ACCENT = (0, 180, 140)
GRAY   = (100, 110, 130)
WHITE  = (255, 255, 255)
LIGHT  = (245, 249, 255)
RED    = (220, 60, 60)


def _s(text: str) -> str:
    """Sanitiza para Latin-1 (fontes core fpdf2)."""
    rep = {
        "—": "-", "–": "-", "’": "'", "‘": "'",
        "“": '"', "”": '"', "•": "*",
        "\xe3": "a", "\xe7": "c", "\xe9": "e", "\xea": "e",
        "\xe0": "a", "\xf5": "o", "\xf3": "o", "\xfa": "u",
        "\xed": "i", "\xe2": "a", "\xf4": "o", "\xe1": "a",
        "\xf1": "n", "\xfc": "u", "\xf6": "o",
    }
    for k, v in rep.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _load(stem: str, year: Optional[int]) -> Optional[pd.DataFrame]:
    if year is not None:
        for ext in (".parquet", ".csv"):
            p = PROCESSED / f"{stem}_{year}{ext}"
            if p.exists():
                return pd.read_parquet(p) if ext == ".parquet" else pd.read_csv(p)
    p2 = PROCESSED / f"{stem}.parquet"
    if p2.exists():
        return pd.read_parquet(p2)
    return None


def generate_pdf_report(year: int = 2025) -> bytes:
    from fpdf import FPDF

    imports_df  = _load("pharma_imports", year)
    top_ncm_df  = _load("top_ncm", year)
    top_pais_df = _load("top_paises", year)
    kpis_df     = _load("kpis_anuais", year)
    anvisa_df = _load("anvisa_medicamentos", year)
    if anvisa_df is None:
        anvisa_df = _load("anvisa_medicamentos", None)
    venc_df     = _load("produtos_vencendo", None)

    # KPIs
    if kpis_df is not None and len(kpis_df) > 0:
        r0        = kpis_df.iloc[0]
        total_fob = float(r0.get("total_fob_usd", 0))
        n_ncm     = int(r0.get("n_ncm", 0))
        n_pais    = int(r0.get("n_pais", 0))
    elif imports_df is not None:
        total_fob = float(imports_df["vl_fob"].sum()) if "vl_fob" in imports_df.columns else 0
        n_ncm     = imports_df["co_ncm"].nunique() if "co_ncm" in imports_df.columns else 0
        n_pais    = imports_df["ds_pais"].nunique() if "ds_pais" in imports_df.columns else 0
    else:
        total_fob = n_ncm = n_pais = 0

    n_anvisa = len(anvisa_df) if anvisa_df is not None else 0
    n_venc   = len(venc_df)   if venc_df   is not None else 0

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(12, 12, 12)

    # ── Cabeçalho ────────────────────────────────────────────────────────────
    pdf.set_fill_color(*DARK)
    pdf.rect(0, 0, 215, 34, style="F")

    pdf.set_xy(12, 8)
    pdf.set_text_color(*ACCENT)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(100, 10, "PharmaIntel BR")

    pdf.set_xy(12, 21)
    pdf.set_text_color(*GRAY)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(100, 5, "Inteligencia de Mercado Farmaceutico")

    pdf.set_xy(120, 10)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(78, 7, f"Relatorio Executivo {year}", align="R")

    pdf.set_xy(120, 20)
    pdf.set_text_color(180, 190, 200)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(78, 5, f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}", align="R")

    pdf.set_y(40)

    # ── Título ───────────────────────────────────────────────────────────────
    pdf.set_text_color(*DARK)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, f"Importacoes Farmaceuticas Brasileiras - {year}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*GRAY)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Capitulos 30 e 90 da TEC  |  Fonte: Comex Stat (MDIC) x ANVISA",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # ── KPI Cards ────────────────────────────────────────────────────────────
    def kpi_card(label: str, value: str, sub: str = "") -> None:
        x = pdf.get_x()
        y = pdf.get_y()
        w = 44
        pdf.set_fill_color(*LIGHT)
        pdf.rect(x, y, w, 22, style="F")
        pdf.set_fill_color(*ACCENT)
        pdf.rect(x, y, 3, 22, style="F")
        pdf.set_xy(x + 5, y + 2)
        pdf.set_text_color(*GRAY)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(w - 6, 4, label.upper())
        pdf.set_xy(x + 5, y + 7)
        pdf.set_text_color(*DARK)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(w - 6, 7, value)
        if sub:
            pdf.set_xy(x + 5, y + 15)
            pdf.set_text_color(*GRAY)
            pdf.set_font("Helvetica", "", 7)
            pdf.cell(w - 6, 4, sub)
        pdf.set_xy(x + w + 4, y)

    fob_b = total_fob / 1e9
    kpi_card("Total FOB (USD)", f"US$ {fob_b:.1f}B", "valor importado")
    kpi_card("NCMs Unicos", f"{n_ncm:,}".replace(",", "."), "posicoes tarifarias")
    kpi_card("Paises Origem", str(n_pais), "fornecedores globais")
    kpi_card("Reg. ANVISA", f"{n_anvisa:,}".replace(",", "."), "medicamentos ativos")

    pdf.ln(28)

    # ── Top 10 NCMs ──────────────────────────────────────────────────────────
    pdf.set_text_color(*DARK)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Top 10 NCMs por Valor FOB", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*ACCENT)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(2)

    if top_ncm_df is not None and len(top_ncm_df) > 0:
        ncm_col  = "co_ncm"  if "co_ncm"  in top_ncm_df.columns else "ncm_8"
        desc_col = "ds_ncm"  if "ds_ncm"  in top_ncm_df.columns else "desc_ncm"
        fob_col  = "vl_fob"  if "vl_fob"  in top_ncm_df.columns else "total_fob_usd"
        top10    = top_ncm_df.nlargest(10, fob_col)
        total_t  = float(top10[fob_col].sum())

        pdf.set_fill_color(*DARK)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(22, 6, "NCM", fill=True)
        pdf.cell(120, 6, "Descricao", fill=True)
        pdf.cell(44, 6, "FOB (USD)", fill=True, align="R",
                 new_x="LMARGIN", new_y="NEXT")

        for i, (_, row) in enumerate(top10.iterrows()):
            bg = LIGHT if i % 2 == 0 else WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(*DARK)
            pdf.set_font("Helvetica", "", 8)
            ncm  = _s(str(row.get(ncm_col, "")))
            desc = _s(str(row.get(desc_col, ""))[:70])
            fob  = float(row.get(fob_col, 0))
            pct  = fob / total_t * 100 if total_t else 0
            pdf.cell(22, 6, ncm, fill=True)
            pdf.cell(120, 6, desc, fill=True)
            pdf.cell(44, 6, f"US$ {fob/1e6:.0f}M  ({pct:.1f}%)", fill=True, align="R",
                     new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    # ── Top 8 Países ─────────────────────────────────────────────────────────
    pdf.set_text_color(*DARK)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Top 8 Paises de Origem", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*ACCENT)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(2)

    if top_pais_df is not None and len(top_pais_df) > 0:
        pais_col = "ds_pais" if "ds_pais" in top_pais_df.columns else "pais"
        fob_col2 = "vl_fob"  if "vl_fob"  in top_pais_df.columns else "total_fob_usd"
        top8     = top_pais_df.nlargest(8, fob_col2)
        total_p  = float(top8[fob_col2].sum())

        pdf.set_fill_color(*DARK)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(96, 6, "Pais", fill=True)
        pdf.cell(54, 6, "FOB (USD)", fill=True, align="R")
        pdf.cell(36, 6, "Share %", fill=True, align="R",
                 new_x="LMARGIN", new_y="NEXT")

        for i, (_, row) in enumerate(top8.iterrows()):
            bg = LIGHT if i % 2 == 0 else WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(*DARK)
            pdf.set_font("Helvetica", "", 8)
            pais = _s(str(row.get(pais_col, "")))
            fob  = float(row.get(fob_col2, 0))
            pct  = fob / total_p * 100 if total_p else 0
            pdf.cell(96, 6, pais, fill=True)
            pdf.cell(54, 6, f"US$ {fob/1e6:.0f}M", fill=True, align="R")
            pdf.cell(36, 6, f"{pct:.1f}%", fill=True, align="R",
                     new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    # ── Alertas ANVISA ───────────────────────────────────────────────────────
    if venc_df is not None and len(venc_df) > 0:
        pdf.set_text_color(*DARK)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7,
                 f"Compliance ANVISA - {n_venc:,} Produtos Monitorados".replace(",", "."),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*ACCENT)
        pdf.line(12, pdf.get_y(), 198, pdf.get_y())
        pdf.ln(2)

        pdf.set_fill_color(*DARK)
        pdf.set_text_color(*WHITE)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(36, 6, "Registro", fill=True)
        pdf.cell(96, 6, "Produto", fill=True)
        pdf.cell(54, 6, "Classe Terapeutica", fill=True,
                 new_x="LMARGIN", new_y="NEXT")

        for i, (_, row) in enumerate(venc_df.head(6).iterrows()):
            bg = LIGHT if i % 2 == 0 else WHITE
            pdf.set_fill_color(*bg)
            pdf.set_text_color(*DARK)
            pdf.set_font("Helvetica", "", 7.5)
            reg  = _s(str(row.get("numero_registro", ""))[:20])
            nome = _s(str(row.get("nome_produto", ""))[:52])
            cls  = _s(str(row.get("classe_terapeutica", ""))[:30])
            pdf.cell(36, 6, reg,  fill=True)
            pdf.cell(96, 6, nome, fill=True)
            pdf.cell(54, 6, cls,  fill=True, new_x="LMARGIN", new_y="NEXT")

    # ── Rodapé ───────────────────────────────────────────────────────────────
    pdf.set_y(-18)
    pdf.set_draw_color(*ACCENT)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(2)
    pdf.set_text_color(*GRAY)
    pdf.set_font("Helvetica", "", 7)
    pdf.cell(140, 5,
             "PharmaIntel BR  |  pharmaintel-br.onrender.com  |  business@globalhealthcareaccess.com")
    pdf.cell(46, 5, f"Pagina {pdf.page_no()}", align="R")

    return bytes(pdf.output())
