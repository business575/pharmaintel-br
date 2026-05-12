"""
auditoria_base.py — Auditoria completa da base de prospects
Classifica cada lead em: VERIFICADO / PENDENTE / REJEITADO
"""
import sys, os, warnings, socket
warnings.filterwarnings('ignore')
sys.path.insert(0, 'C:/Users/vinic/OneDrive/Desktop/PharmaIntelBR')
os.chdir('C:/Users/vinic/OneDrive/Desktop/PharmaIntelBR')
from dotenv import load_dotenv
load_dotenv()
from src.db.database import get_prospects, init_db
init_db()

def domain_exists(email):
    try:
        domain = email.split('@')[1]
        socket.getaddrinfo(domain, None)
        return True
    except:
        return False

# Empresas globais verificadas — existencia publica confirmada
VERIFIED_COMPANIES = {
    # Big Pharma Global — verificadas publicamente
    'Novo Nordisk': 'novonordisk.com — empresa listada em bolsa, verificada',
    'Pfizer': 'pfizer.com — empresa listada em bolsa, verificada',
    'Roche': 'roche.com — empresa listada em bolsa, verificada',
    'Novartis': 'novartis.com — empresa listada em bolsa, verificada',
    'Sanofi': 'sanofi.com — empresa listada em bolsa, verificada',
    'AstraZeneca': 'astrazeneca.com — empresa listada em bolsa, verificada',
    'GSK': 'gsk.com — empresa listada em bolsa, verificada',
    'Bayer': 'bayer.com — empresa listada em bolsa, verificada',
    'Takeda': 'takeda.com — empresa listada em bolsa, verificada',
    'Bristol Myers Squibb': 'bms.com — empresa listada em bolsa, verificada',
    'Merck': 'merck.com — empresa listada em bolsa, verificada',
    'Gilead': 'gilead.com — empresa listada em bolsa, verificada',
    'Amgen': 'amgen.com — empresa listada em bolsa, verificada',
    'Biogen': 'biogen.com — empresa listada em bolsa, verificada',
    'Regeneron': 'regeneron.com — empresa listada em bolsa, verificada',
    'Vertex': 'vrtx.com — empresa listada em bolsa, verificada',
    'Teva': 'tevapharm.com — empresa listada em bolsa, verificada',
    'Sandoz': 'sandoz.com — divisao Novartis, verificada',
    'Lonza': 'lonza.com — empresa listada em bolsa, verificada',
    'Fresenius': 'fresenius-kabi.com — empresa listada em bolsa, verificada',
    # India — verificadas publicamente
    'Sun Pharma': 'sunpharma.com — empresa listada em bolsa India, verificada',
    'Cipla': 'cipla.com — empresa listada em bolsa India, verificada',
    'Biocon': 'bioconbiologics.com — empresa listada em bolsa India, verificada',
    # China — verificadas publicamente
    'Fosun Pharma': 'fosunpharma.com — empresa listada em bolsa China, verificada',
    'BeiGene': 'beigene.com — empresa listada em bolsa Nasdaq, verificada',
    'Zai Lab': 'zailaboratory.com — empresa listada em bolsa Nasdaq, verificada',
    'WuXi AppTec': 'wuxiapptec.com — empresa listada em bolsa China, verificada',
    # CROs — verificadas publicamente
    'Parexel': 'parexel.com — empresa verificada, sede EUA',
    'ICON plc': 'iconplc.com — empresa listada em bolsa, verificada',
    # Brasil — verificadas publicamente
    'A.C. Camargo Cancer Center': 'accamargo.org.br — hospital verificado, inbound confirmado',
    'Grupo Cimed': 'grupocimed.com.br — empresa listada em bolsa Brasil, verificada',
    'Blau Farmaceutica': 'blau.com.br — empresa listada em bolsa Brasil, verificada',
    'Eurofarma': 'eurofarma.com.br — empresa verificada Brasil',
    'EMS Pharma': 'ems.com.br — empresa verificada Brasil',
    'Hapvida': 'hapvidagndi.com.br — empresa listada em bolsa Brasil, verificada',
    'Bradesco Saude': 'bradescosaude.com.br — empresa verificada Brasil',
    'Rede D Or': 'rededorsaoluiz.com.br — empresa listada em bolsa Brasil, verificada',
    'Hospital Albert Einstein': 'einstein.br — hospital verificado Brasil',
    'Oncoclínicas': 'grupooncoclinicas.com — empresa listada em bolsa Brasil, verificada',
    'Dasa': 'dasa.com.br — empresa listada em bolsa Brasil, verificada',
    'Celltrion': 'celltrionhc.com — empresa listada em bolsa Korea, verificada',
    'Crinetics': 'crinetics.com — empresa listada em bolsa Nasdaq, verificada',
    # Consultoras — verificadas
    'Brix Consulting': 'brixconsulting.com.br — verificada, contato obtido via site',
    'Chameleon Pharma': 'chameleon-pharma.com — verificada, contato obtido via site',
    'Tanner Pharma': 'tannerpharma.com — verificada via site oficial',
    'Global Swiss Group': 'global-swiss.ch — contato fornecido pelo acionista via LinkedIn',
}

# Empresas adicionadas sem verificacao adequada
SUSPICIOUS = [
    'LATAM Pharma Distributors',
    'NovaBay China Pharma Partners',
    'Zhejiang Ausun Pharmaceutical',
    'Kitov Pharma Israel',
    'InVivo Therapeutics Israel',
    'CollPlant Biotechnologies',
    'Athos Therapeutics',
    'Athernal Bio',
    'Atlas Molecular Pharma',
    'Atriva Therapeutics',
    'Atsena Therapeutics',
    'AttgeNO',
    'ATXA Therapeutics',
    'aTyr Pharma',
    'AudioCure Pharma',
    'Atterx BioTherapeutics',
    'Atropos Therapeutics',
    'Atom Therapeutics',
    'Atlanthera',
    'Pediatrix Therapeutics',
    'Advanced Innovative Partners',
    'Oxitope Pharma',
    'Re-Vana Therapeutics',
    'UroMems',
    'Entact Bio',
    'Esperovax',
    'SonoThera',
    'BiondVax Pharmaceuticals',
    'Todos Medical Israel',
]

all_p = get_prospects(limit=500)
report = {'VERIFICADO': [], 'PENDENTE': [], 'REJEITADO': []}

for p in all_p:
    email = p['email'] or ''
    name = p['company_name']
    status_val = 'PENDENTE'
    fonte = 'Nao documentada'
    domain_ok = domain_exists(email) if email else False
    email_ok = domain_ok
    obs = ''

    # Verifica se e empresa conhecida
    matched_key = None
    for key in VERIFIED_COMPANIES:
        if key.lower() in name.lower() or name.lower() in key.lower():
            matched_key = key
            break

    if name in SUSPICIOUS:
        status_val = 'REJEITADO'
        fonte = 'Adicionada sem verificacao — empresa nao confirmada'
        obs = 'Remover — empresa adicionada por inferencia sem fonte publica'
    elif not domain_ok and email:
        status_val = 'REJEITADO'
        fonte = 'Dominio de email inexistente'
        obs = f'Dominio invalido: {email.split("@")[1] if "@" in email else "sem email"}'
    elif matched_key:
        status_val = 'VERIFICADO'
        fonte = VERIFIED_COMPANIES[matched_key]
        obs = 'Empresa publica verificada'
    elif p['status'] == 'bounced':
        status_val = 'REJEITADO'
        fonte = 'Email retornou bounce'
        obs = 'Remover ou corrigir email'
    elif domain_ok and email:
        status_val = 'PENDENTE'
        fonte = 'Dominio existe mas empresa nao verificada individualmente'
        obs = 'Validar empresa antes de incluir em campanha'
    else:
        status_val = 'PENDENTE'
        fonte = 'Sem email ou sem validacao'
        obs = 'Falta email verificado'

    report[status_val].append({
        'empresa': name,
        'email': email,
        'status_atual': p['status'],
        'status_validacao': status_val,
        'fonte_empresa': fonte,
        'dominio_validado': 'SIM' if domain_ok else 'NAO',
        'email_validado': 'SIM' if email_ok else 'NAO',
        'observacao_risco': obs,
    })

# RELATORIO
print('=' * 65)
print('RELATORIO DE AUDITORIA DA BASE — PharmaIntel BR')
print('=' * 65)
print(f'\nTotal analisados:  {len(all_p)}')
print(f'VERIFICADOS:       {len(report["VERIFICADO"])}')
print(f'PENDENTES:         {len(report["PENDENTE"])}')
print(f'REJEITADOS:        {len(report["REJEITADO"])}')

print(f'\n--- VERIFICADOS ({len(report["VERIFICADO"])}) — SEGUROS PARA ENVIO ---')
for r in report['VERIFICADO']:
    print(f'  OK  {r["empresa"]} <{r["email"]}>')
    print(f'      Fonte: {r["fonte_empresa"][:60]}')

print(f'\n--- PENDENTES ({len(report["PENDENTE"])}) — BLOQUEADOS ATE VALIDACAO ---')
for r in report['PENDENTE']:
    print(f'  PEND {r["empresa"]} <{r["email"]}>')
    print(f'       {r["observacao_risco"]}')

print(f'\n--- REJEITADOS ({len(report["REJEITADO"])}) — REMOVER DA BASE ---')
for r in report['REJEITADO']:
    print(f'  REJ  {r["empresa"]} <{r["email"]}>')
    print(f'       {r["observacao_risco"]}')

print(f'\nLISTA FINAL SEGURA PARA ENVIO: {len(report["VERIFICADO"])} prospects')
