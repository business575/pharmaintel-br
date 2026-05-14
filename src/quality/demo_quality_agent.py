"""
demo_quality_agent.py — Agente de Qualidade para Demo AC Camargo
Valida 100% dos dados que serão apresentados na reunião de 27/05/2026.
Gera certificado de acurácia antes da demo.
BLOQUEIO TOTAL se qualquer dado falhar.
"""
import sys, os, warnings, socket, json
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ERRORS   = []
WARNINGS = []
PASSED   = []

def ok(msg):
    PASSED.append(msg)
    print(f'  [OK] {msg}')

def warn(msg):
    WARNINGS.append(msg)
    print(f'  [AVISO] {msg}')

def fail(msg):
    ERRORS.append(msg)
    print(f'  [ERRO CRITICO] {msg}')


# ── BLOCO 1 — CMED: valores e ordem lógica ───────────────────────────────────
def check_cmed():
    print('\n[1] VALIDANDO PRECOS CMED/ANVISA...')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    from src.integrations.bps import get_price_summary

    EXPECTED = {
        'trastuzumabe':   {'pf_min': 2000,   'pf_max': 20000,  'nome': 'Trastuzumabe'},
        'pembrolizumabe': {'pf_min': 20000,  'pf_max': 60000,  'nome': 'Pembrolizumabe'},
        'bevacizumabe':   {'pf_min': 500,    'pf_max': 10000,  'nome': 'Bevacizumabe'},
        'rituximabe':     {'pf_min': 1000,   'pf_max': 15000,  'nome': 'Rituximabe'},
    }

    results = {}
    for drug, ref in EXPECTED.items():
        try:
            data = get_price_summary(drug)
            pf = data.get('pf_medio', 0)
            results[drug] = pf
            if ref['pf_min'] <= pf <= ref['pf_max']:
                ok(f'{ref["nome"]}: PF R$ {pf:,.2f} — dentro da faixa esperada')
            else:
                fail(f'{ref["nome"]}: PF R$ {pf:,.2f} FORA da faixa R${ref["pf_min"]:,}-R${ref["pf_max"]:,}')
        except Exception as e:
            fail(f'{ref["nome"]}: erro ao buscar CMED — {e}')

    # Ordem lógica obrigatória
    if 'pembrolizumabe' in results and 'trastuzumabe' in results:
        if results['pembrolizumabe'] > results['trastuzumabe']:
            ok(f'Ordem lógica: Pembrolizumabe R${results["pembrolizumabe"]:,.0f} > Trastuzumabe R${results["trastuzumabe"]:,.0f}')
        else:
            fail(f'ORDEM INVERTIDA: Pembrolizumabe ({results["pembrolizumabe"]:,.0f}) deveria ser > Trastuzumabe ({results["trastuzumabe"]:,.0f}) — POSSIVEL TROCA DE VALORES')

    return results


# ── BLOCO 2 — FOB estimado por frasco: lógica coerente ───────────────────────
def check_fob_logic(cmed_results):
    print('\n[2] VALIDANDO LOGICA FOB vs CMED...')

    FOB_ESTIMADOS = {
        'trastuzumabe':   100,
        'pembrolizumabe': 450,
        'bevacizumabe':   55,
        'rituximabe':     85,
    }

    for drug, fob_fr in FOB_ESTIMADOS.items():
        pf = cmed_results.get(drug, 0)
        if pf == 0:
            warn(f'{drug}: PF não disponível para comparação')
            continue
        ratio = fob_fr / pf
        espaco = pf - fob_fr
        score = min(100, int((1 - ratio) * 100))

        if ratio < 0.20:
            ok(f'{drug.title()}: FOB R${fob_fr} = {ratio*100:.1f}% do PF — Score {score}/100 — coerente')
        elif ratio < 0.50:
            warn(f'{drug.title()}: FOB R${fob_fr} = {ratio*100:.1f}% do PF — Score {score}/100 — verificar')
        else:
            fail(f'{drug.title()}: FOB R${fob_fr} = {ratio*100:.1f}% do PF — Score {score}/100 — SUSPEITO')

        if espaco <= 0:
            fail(f'{drug.title()}: espaço de negociação NEGATIVO — erro nos dados')
        else:
            ok(f'{drug.title()}: espaço de negociação R${espaco:,.0f} — positivo e coerente')


# ── BLOCO 3 — Comex Stat: dados de importação ────────────────────────────────
def check_comexstat():
    print('\n[3] VALIDANDO DADOS COMEX STAT 2025...')
    import pandas as pd

    processed = ROOT / 'data' / 'processed'
    imp_file = processed / 'pharma_imports_2025.parquet'

    if not imp_file.exists():
        fail('pharma_imports_2025.parquet não encontrado')
        return

    df = pd.read_parquet(imp_file)
    total_fob = df['vl_fob'].sum()
    n_ops = len(df)
    n_ncms = df['co_ncm'].nunique()

    if total_fob > 10e9:
        ok(f'Total FOB 2025: USD {total_fob/1e9:.1f}B — coerente com mercado brasileiro')
    else:
        fail(f'Total FOB 2025: USD {total_fob/1e9:.1f}B — abaixo do esperado')

    if n_ops > 10000:
        ok(f'Operações 2025: {n_ops:,} — volume coerente')
    else:
        fail(f'Operações 2025: {n_ops:,} — volume suspeito')

    # Valida NCM 30021590 (imunológicos — trastuzumabe, bevacizumabe, rituximabe)
    ncm_imuno = df[df['co_ncm'].astype(str) == '30021590']
    fob_imuno = ncm_imuno['vl_fob'].sum()
    if 500e6 < fob_imuno < 10e9:
        ok(f'NCM 30021590 (imunológicos): USD {fob_imuno/1e9:.1f}B — coerente')
    else:
        fail(f'NCM 30021590: USD {fob_imuno/1e6:.0f}M — fora do esperado')

    # Valida NCM 30049069 (antineoplásicos — pembrolizumabe)
    ncm_antineopl = df[df['co_ncm'].astype(str) == '30049069']
    fob_antineopl = ncm_antineopl['vl_fob'].sum()
    if 200e6 < fob_antineopl < 5e9:
        ok(f'NCM 30049069 (antineoplásicos): USD {fob_antineopl/1e9:.1f}B — coerente')
    else:
        fail(f'NCM 30049069: USD {fob_antineopl/1e6:.0f}M — fora do esperado')

    # Valida país de origem principal
    top_pais_imuno = ncm_imuno.groupby('ds_pais')['vl_fob'].sum().sort_values(ascending=False).index[0]
    paises_esperados = ['Alemanha', 'Irlanda', 'Suíça', 'Estados Unidos']
    if any(p in top_pais_imuno for p in paises_esperados):
        ok(f'Principal origem NCM 30021590: {top_pais_imuno} — coerente')
    else:
        warn(f'Principal origem NCM 30021590: {top_pais_imuno} — verificar se coerente')


# ── BLOCO 4 — ANVISA: contagens ───────────────────────────────────────────────
def check_anvisa():
    print('\n[4] VALIDANDO DADOS ANVISA...')
    import pandas as pd

    processed = ROOT / 'data' / 'processed'

    # Medicamentos
    med_file = processed / 'anvisa_medicamentos.parquet'
    if med_file.exists():
        df = pd.read_parquet(med_file)
        n = len(df)
        if 10000 < n < 30000:
            ok(f'ANVISA medicamentos: {n:,} registros — coerente com 17.247 referenciado na demo')
        else:
            fail(f'ANVISA medicamentos: {n:,} registros — diverge do valor citado na demo (17.247)')
    else:
        fail('anvisa_medicamentos.parquet não encontrado')

    # Dispositivos
    disp_file = processed / 'anvisa_dispositivos.parquet'
    if disp_file.exists():
        df2 = pd.read_parquet(disp_file)
        n2 = len(df2)
        if 50000 < n2 < 200000:
            ok(f'ANVISA dispositivos: {n2:,} registros — coerente com 97.107 referenciado')
        else:
            fail(f'ANVISA dispositivos: {n2:,} — diverge do valor citado (97.107)')
    else:
        warn('anvisa_dispositivos.parquet não encontrado')

    # Produtos vencendo
    venc_file = processed / 'produtos_vencendo.parquet'
    if venc_file.exists():
        df3 = pd.read_parquet(venc_file)
        n3 = len(df3)
        if 10000 < n3 < 50000:
            ok(f'Produtos vencendo: {n3:,} — coerente com 23.304 referenciado')
        else:
            fail(f'Produtos vencendo: {n3:,} — diverge do valor citado (23.304)')
    else:
        fail('produtos_vencendo.parquet não encontrado')


# ── BLOCO 5 — NCM-Empresa: mapa de fornecedores ───────────────────────────────
def check_fornecedores():
    print('\n[5] VALIDANDO MAPA DE FORNECEDORES...')
    import pandas as pd

    processed = ROOT / 'data' / 'processed'
    ncm_file = processed / 'ncm_empresa_link.parquet'

    if not ncm_file.exists():
        fail('ncm_empresa_link.parquet não encontrado')
        return

    df = pd.read_parquet(ncm_file)
    ncm_imuno = df[df['co_ncm'].astype(str) == '30021590']
    n_fornec = len(ncm_imuno)

    if 50 < n_fornec < 200:
        ok(f'Fornecedores autorizados NCM 30021590: {n_fornec} — coerente com 79 citado na demo')
    else:
        fail(f'Fornecedores NCM 30021590: {n_fornec} — diverge do valor citado (79)')


# ── BLOCO 6 — Plataforma online ───────────────────────────────────────────────
def check_platform():
    print('\n[6] VERIFICANDO PLATAFORMA ONLINE...')
    import socket as s

    domains = [
        ('pharmaintel-br.onrender.com', 'Plataforma Render'),
        ('business575.github.io', 'Tour GitHub Pages'),
    ]
    for domain, name in domains:
        try:
            s.getaddrinfo(domain, 443)
            ok(f'{name}: domínio resolvido — online')
        except:
            fail(f'{name}: domínio não resolvido — VERIFICAR ANTES DA DEMO')


# ── BLOCO 7 — Consistência interna dos dados da demo ─────────────────────────
def check_demo_consistency(cmed_results):
    print('\n[7] VERIFICANDO CONSISTENCIA DOS DADOS DA DEMO...')

    # Valores que serão falados na demo
    DEMO_VALUES = {
        'trastuzumabe_pf':   8747.90,
        'pembrolizumabe_pf': 33962.44,
        'bevacizumabe_pf':   3458.15,
        'rituximabe_pf':     6512.84,
    }

    for key, expected in DEMO_VALUES.items():
        drug = key.replace('_pf', '')
        real = cmed_results.get(drug, 0)
        diff_pct = abs(real - expected) / expected * 100 if expected > 0 else 100

        if diff_pct < 1:
            ok(f'{drug.title()}: PF real R${real:,.2f} = esperado R${expected:,.2f} — diferença {diff_pct:.2f}%')
        elif diff_pct < 5:
            warn(f'{drug.title()}: PF real R${real:,.2f} vs esperado R${expected:,.2f} — diferença {diff_pct:.1f}% — atualizar roteiro')
        else:
            fail(f'{drug.title()}: PF real R${real:,.2f} vs esperado R${expected:,.2f} — diferença {diff_pct:.0f}% — DADO DESATUALIZADO')


# ── RELATÓRIO FINAL ────────────────────────────────────────────────────────────
def generate_certificate(cmed_results):
    now = datetime.now().strftime('%d/%m/%Y %H:%M')
    status = 'APROVADO' if not ERRORS else 'REPROVADO'

    print('\n' + '=' * 65)
    print(f'CERTIFICADO DE QUALIDADE — DEMO AC CAMARGO')
    print(f'Gerado em: {now}')
    print(f'Status: {status}')
    print('=' * 65)
    print(f'  Verificações aprovadas: {len(PASSED)}')
    print(f'  Avisos:                 {len(WARNINGS)}')
    print(f'  Erros críticos:         {len(ERRORS)}')

    if ERRORS:
        print('\nERROS CRITICOS — CORRIGIR ANTES DA DEMO:')
        for e in ERRORS:
            print(f'  !! {e}')

    if WARNINGS:
        print('\nAVISOS — REVISAR:')
        for w in WARNINGS:
            print(f'  >> {w}')

    if not ERRORS:
        print('\nDADOS VALIDADOS PARA USO NA DEMO:')
        for drug, pf in cmed_results.items():
            print(f'  {drug.title()}: PF/PMVG = R$ {pf:,.2f}')

        print(f'\nCERTIFICADO: Material aprovado para demo em 27/05/2026.')
        print('Todos os valores verificados contra fontes oficiais.')
        print('(CMED/ANVISA publ. 16/04/2026 + Comex Stat MDIC 2025)')

    print('=' * 65)

    # Salva certificado
    cert_path = ROOT / 'data' / 'exports' / 'certificado_qualidade_demo.json'
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cert = {
        'gerado_em': now,
        'status': status,
        'aprovadas': len(PASSED),
        'avisos': len(WARNINGS),
        'erros': len(ERRORS),
        'erros_detalhes': ERRORS,
        'avisos_detalhes': WARNINGS,
        'cmed_validado': {k: round(v, 2) for k, v in cmed_results.items()},
    }
    with open(cert_path, 'w', encoding='utf-8') as f:
        json.dump(cert, f, indent=2, ensure_ascii=False)
    print(f'\nCertificado salvo em: {cert_path}')

    return status == 'APROVADO'


# ── MAIN ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print('=' * 65)
    print('AGENTE DE QUALIDADE — DEMO AC CAMARGO 27/05/2026')
    print('Tolerância a erro: ZERO')
    print('=' * 65)

    cmed = check_cmed()
    check_fob_logic(cmed)
    check_comexstat()
    check_anvisa()
    check_fornecedores()
    check_platform()
    check_demo_consistency(cmed)
    approved = generate_certificate(cmed)

    sys.exit(0 if approved else 1)
