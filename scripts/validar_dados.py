"""
validar_dados.py — Controle de Qualidade PharmaIntel BR
Executa antes de qualquer geracao de material (PDF, email, relatorio).
Valida dados criticos e bloqueia geracao se encontrar erro.
"""
import sys, os, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'C:/Users/vinic/OneDrive/Desktop/PharmaIntelBR')
os.chdir('C:/Users/vinic/OneDrive/Desktop/PharmaIntelBR')
from dotenv import load_dotenv
load_dotenv()

ERRORS = []
WARNINGS = []

def check(condition, msg_ok, msg_fail, critical=True):
    if condition:
        print(f'  OK  {msg_ok}')
    else:
        print(f'  ERRO {msg_fail}')
        if critical:
            ERRORS.append(msg_fail)
        else:
            WARNINGS.append(msg_fail)

print('='*60)
print('CONTROLE DE QUALIDADE — PharmaIntel BR')
print('='*60)

# ── 1. CMED — verifica PF de moleculas criticas ──────────────
print('\n[1] Validando precos CMED/ANVISA...')
from src.integrations.bps import get_price_summary

# Valores de referencia conhecidos e verificados
CMED_REFERENCE = {
    'trastuzumabe':   {'pf_min': 2000,   'pf_max': 20000,  'nome_ref': 'Trastuzumabe'},
    'pembrolizumabe': {'pf_min': 20000,  'pf_max': 60000,  'nome_ref': 'Pembrolizumabe'},
    'bevacizumabe':   {'pf_min': 1000,   'pf_max': 8000,   'nome_ref': 'Bevacizumabe'},
    'rituximabe':     {'pf_min': 2000,   'pf_max': 15000,  'nome_ref': 'Rituximabe'},
    'enoxaparina':    {'pf_min': 10,     'pf_max': 2000,   'nome_ref': 'Enoxaparina'},
}

cmed_results = {}
for drug, ref in CMED_REFERENCE.items():
    try:
        data = get_price_summary(drug)
        pf = data.get('pf_medio', 0)
        cmed_results[drug] = pf
        check(
            ref['pf_min'] <= pf <= ref['pf_max'],
            f"{ref['nome_ref']}: PF R${pf:,.2f} (faixa esperada: R${ref['pf_min']:,}-R${ref['pf_max']:,})",
            f"{ref['nome_ref']}: PF R${pf:,.2f} FORA da faixa esperada R${ref['pf_min']:,}-R${ref['pf_max']:,} — VERIFIQUE!",
            critical=True
        )
    except Exception as e:
        check(False, '', f"{ref['nome_ref']}: Erro ao buscar CMED — {e}", critical=True)

# ── 2. Verifica ordem das moleculas (erro de troca) ──────────
print('\n[2] Verificando ordem logica dos precos...')
if 'trastuzumabe' in cmed_results and 'pembrolizumabe' in cmed_results:
    pf_trast = cmed_results['trastuzumabe']
    pf_pemb  = cmed_results['pembrolizumabe']
    check(
        pf_pemb > pf_trast,
        f'Pembrolizumabe (R${pf_pemb:,.0f}) > Trastuzumabe (R${pf_trast:,.0f}) — ordem correta',
        f'ALERTA: Pembrolizumabe ({pf_pemb:,.0f}) deveria ser > Trastuzumabe ({pf_trast:,.0f}) — possivel troca de valores!',
        critical=True
    )

# ── 3. Comex Stat — verifica dados de importacao ─────────────
print('\n[3] Validando dados Comex Stat...')
import pandas as pd
from pathlib import Path
processed = Path('data/processed')

for year in [2025, 2026]:
    try:
        df = pd.read_parquet(processed / f'pharma_imports_{year}.parquet')
        fob_total = df['vl_fob'].sum()
        n_ops = len(df)
        check(fob_total > 1e9,
              f'Imports {year}: USD {fob_total/1e9:.1f}B | {n_ops:,} operacoes',
              f'Imports {year}: total suspeito USD {fob_total/1e6:.0f}M — verificar dados',
              critical=False)
        check('co_ncm' in df.columns and 'vl_fob' in df.columns,
              f'Imports {year}: colunas co_ncm e vl_fob presentes',
              f'Imports {year}: colunas essenciais ausentes!',
              critical=True)
    except Exception as e:
        check(False, '', f'Imports {year}: arquivo nao encontrado — {e}', critical=True)

# ── 4. ANVISA — verifica registros ──────────────────────────
print('\n[4] Validando dados ANVISA...')
try:
    anvisa = pd.read_parquet(processed / 'anvisa_medicamentos.parquet')
    check(len(anvisa) > 10000,
          f'ANVISA medicamentos: {len(anvisa):,} registros',
          f'ANVISA medicamentos: apenas {len(anvisa)} registros — suspeito',
          critical=False)
except Exception as e:
    check(False, '', f'ANVISA: {e}', critical=True)

# ── 5. Groq API ──────────────────────────────────────────────
print('\n[5] Validando Groq API...')
try:
    from groq import Groq
    c = Groq(api_key=os.getenv('GROQ_API_KEY',''))
    c.chat.completions.create(model='llama-3.3-70b-versatile',
                              messages=[{'role':'user','content':'ok'}], max_tokens=5)
    check(True, 'Groq API: funcionando', '')
except Exception as e:
    check(False, '', f'Groq API: {e}', critical=False)

# ── 6. Gmail SMTP ────────────────────────────────────────────
print('\n[6] Validando Gmail SMTP...')
try:
    import smtplib
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login(os.getenv('GMAIL_USER',''), os.getenv('GMAIL_APP_PASSWORD',''))
    s.quit()
    check(True, 'Gmail SMTP: funcionando', '')
except Exception as e:
    check(False, '', f'Gmail SMTP: {e}', critical=False)

# ── 7. Verifica dominios invalidos no banco ──────────────────
print('\n[7] Verificando dominios de email no banco...')
import socket as _socket
from src.db.database import get_prospects as _gp
_prospects = _gp(limit=500)
_fake = []
for _p in _prospects:
    if not _p['email'] or _p['status'] == 'bounced':
        continue
    try:
        _domain = _p['email'].split('@')[1]
        _socket.getaddrinfo(_domain, None)
    except:
        _fake.append(_p['email'])
check(len(_fake) == 0,
      f'Todos os dominios ativos sao validos ({len(_prospects)} prospects)',
      f'{len(_fake)} emails com dominio invalido: {_fake[:3]}',
      critical=False)

# ── RESULTADO FINAL ──────────────────────────────────────────
print('\n' + '='*60)
if ERRORS:
    print(f'REPROVADO — {len(ERRORS)} erro(s) critico(s):')
    for e in ERRORS:
        print(f'  BLOQUEADO: {e}')
    print('\nNAO GERAR MATERIAL ATE CORRIGIR OS ERROS ACIMA.')
    sys.exit(1)
else:
    print(f'APROVADO — Dados validados. {len(WARNINGS)} aviso(s).')
    if WARNINGS:
        for w in WARNINGS:
            print(f'  AVISO: {w}')
    print('\nMaterial pode ser gerado com seguranca.')
    sys.exit(0)
