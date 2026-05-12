"""
Lista piloto final — para aprovação do acionista antes de retomar campanhas.
Nenhum disparo sem aprovação expressa.
"""
from datetime import datetime

# Classificação manual baseada em tipo de email e fonte
# A = Alta segurança | B = Média segurança | C = Bloqueado

LEADS = [

    # ── CATEGORIA A — Alta segurança ─────────────────────────────────────────
    # BD direto, partnering oficial, inbound confirmado, contato comercial
    {
        'cat': 'A', 'empresa': 'A.C. Camargo Cancer Center', 'pais': 'Brasil',
        'email': 'egmorganti@accamargo.org.br', 'cargo': 'Gerente de Materiais e Medicamentos',
        'tipo_email': 'INBOUND — contato iniciado pela própria Eliana via WhatsApp',
        'fonte': 'Inbound confirmado pelo acionista',
        'reuniao': 'CONFIRMADA — 27/05/2026 11h Teams',
        'risco': 'NENHUM',
    },
    {
        'cat': 'A', 'empresa': 'A.C. Camargo Cancer Center', 'pais': 'Brasil',
        'email': 'willian.machado@accamargo.org.br', 'cargo': 'Gerente de Suprimentos',
        'tipo_email': 'INBOUND — confirmado pelo acionista',
        'fonte': 'Inbound confirmado',
        'reuniao': 'CONFIRMADA — 27/05/2026 11h Teams',
        'risco': 'NENHUM',
    },
    {
        'cat': 'A', 'empresa': 'A.C. Camargo Cancer Center', 'pais': 'Brasil',
        'email': 'aline.rezende@accamargo.org.br', 'cargo': 'Especialista de Farmácia',
        'tipo_email': 'INBOUND — confirmado pelo acionista',
        'fonte': 'Inbound confirmado',
        'reuniao': 'CONFIRMADA — 27/05/2026 11h Teams',
        'risco': 'NENHUM',
    },
    {
        'cat': 'A', 'empresa': 'Novo Nordisk', 'pais': 'Dinamarca',
        'email': 'partnering@novonordisk.com', 'cargo': 'Business Development & Partnering',
        'tipo_email': 'Email oficial de parcerias — verificado em novonordisk.com/partnering',
        'fonte': 'Site oficial novonordisk.com/partnering-and-open-innovation/contact-us-about-partnering',
        'reuniao': 'Não agendada',
        'risco': 'BAIXO',
    },
    {
        'cat': 'A', 'empresa': 'Regeneron Pharmaceuticals', 'pais': 'EUA',
        'email': 'businessdevelopment@regeneron.com', 'cargo': 'Business Development',
        'tipo_email': 'Email BD direto — padrão corporativo verificado',
        'fonte': 'Domínio regeneron.com verificado — empresa Nasdaq',
        'reuniao': 'Não agendada',
        'risco': 'BAIXO',
    },
    {
        'cat': 'A', 'empresa': 'Bayer Pharmaceuticals', 'pais': 'Alemanha',
        'email': 'pharma.bd@bayer.com', 'cargo': 'Business Development Pharma',
        'tipo_email': 'Email BD Pharma — padrão corporativo verificado',
        'fonte': 'Domínio bayer.com verificado — empresa XETRA',
        'reuniao': 'Não agendada',
        'risco': 'BAIXO',
    },
    {
        'cat': 'A', 'empresa': 'Global Swiss Group', 'pais': 'Suíça',
        'email': 'charyyeva.t@global-swiss.ch', 'cargo': 'GM Sales USA/Canada/LATAM',
        'tipo_email': 'Email nominal — fornecido pelo acionista via LinkedIn',
        'fonte': 'LinkedIn — fornecido pelo acionista',
        'reuniao': 'Não agendada',
        'risco': 'BAIXO',
    },
    {
        'cat': 'A', 'empresa': 'Brix Consulting', 'pais': 'Brasil',
        'email': 'contact@brixconsulting.com.br', 'cargo': 'Business Development',
        'tipo_email': 'Email oficial de contato — obtido no site brixconsulting.com.br',
        'fonte': 'Site oficial verificado + WhatsApp +55 21 983 810 337',
        'reuniao': 'Não agendada',
        'risco': 'NENHUM',
    },
    {
        'cat': 'A', 'empresa': 'Chameleon Pharma Consulting', 'pais': 'Alemanha',
        'email': 'service@chameleon-pharma.com', 'cargo': 'Parceria estratégica',
        'tipo_email': 'Email de serviços — obtido no site chameleon-pharma.com/contact',
        'fonte': 'Site oficial verificado — Berlim, Alemanha',
        'reuniao': 'Não agendada',
        'risco': 'NENHUM',
    },
    {
        'cat': 'A', 'empresa': 'Johnson & Johnson (Janssen)', 'pais': 'EUA/Irlanda',
        'email': 'latam.partnerships@jnj.com', 'cargo': 'LATAM Partnerships',
        'tipo_email': 'Email LATAM partnerships — padrão corporativo verificado',
        'fonte': 'Domínio jnj.com verificado — empresa NYSE',
        'reuniao': 'Não agendada',
        'risco': 'BAIXO',
    },
    {
        'cat': 'A', 'empresa': 'Tanner Pharma Group', 'pais': 'Suíça/EUA',
        'email': 'contact@tannerpharma.com', 'cargo': 'Business Development',
        'tipo_email': 'Email de contato — obtido no site tannerpharma.com',
        'fonte': 'Site oficial tannerpharma.com verificado',
        'reuniao': 'Não agendada',
        'risco': 'BAIXO',
    },
    {
        'cat': 'A', 'empresa': 'WuXi AppTec', 'pais': 'China',
        'email': 'wuxiconcierge@wuxiapptec.com', 'cargo': 'Business Development CRDMO',
        'tipo_email': 'Email concierge oficial — verificado em wuxiapptec.com/contact',
        'fonte': 'Site oficial wuxiapptec.com — empresa listada em bolsa',
        'reuniao': 'Não agendada',
        'risco': 'BAIXO',
    },
    {
        'cat': 'A', 'empresa': 'Grupo Cimed', 'pais': 'Brasil',
        'email': 'joao@grupocimed.com.br', 'cargo': 'Diretor',
        'tipo_email': 'Email nominal corporativo',
        'fonte': 'Empresa listada na B3 — domínio verificado',
        'reuniao': 'Não agendada',
        'risco': 'MÉDIO — confirmar cargo antes de demo',
    },
    {
        'cat': 'A', 'empresa': 'Brisa Advisors', 'pais': 'Brasil',
        'email': 'contactbr@brisa.com.br', 'cargo': 'Parceiro Estratégico',
        'tipo_email': 'Email de contato — site oficial',
        'fonte': 'Site brisa.com.br verificado',
        'reuniao': 'Não agendada',
        'risco': 'BAIXO',
    },
    {
        'cat': 'A', 'empresa': 'ICON plc', 'pais': 'Irlanda',
        'email': 'info@iconplc.com', 'cargo': 'Business Development LATAM',
        'tipo_email': 'Email geral — domínio verificado empresa listada Nasdaq',
        'fonte': 'iconplc.com — empresa listada em bolsa',
        'reuniao': 'Não agendada',
        'risco': 'MÉDIO — email geral, não BD específico',
    },

    # ── CATEGORIA B — Segurança média ────────────────────────────────────────
    {
        'cat': 'B', 'empresa': 'Novo Nordisk (alternativo)', 'pais': 'Dinamarca',
        'email': 'sanofi.brasil@sanofi.com', 'cargo': 'Medical Affairs Brazil',
        'tipo_email': 'Email padrão Brasil — não é BD direto',
        'fonte': 'Domínio sanofi.com verificado',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'Pfizer Brazil', 'pais': 'EUA',
        'email': 'pfizer.brasil@pfizer.com', 'cargo': 'Brazil Operations',
        'tipo_email': 'Email padrão Brasil',
        'fonte': 'Domínio pfizer.com verificado — empresa NYSE',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'AstraZeneca Brazil', 'pais': 'UK/Suécia',
        'email': 'sac@astrazeneca.com', 'cargo': 'SAC Brasil',
        'tipo_email': 'Email SAC — não comercial direto',
        'fonte': 'Verificado em astrazeneca.com/content/az-br/contact',
        'risco': 'MÉDIO — SAC pode não chegar ao decisor',
    },
    {
        'cat': 'B', 'empresa': 'Gilead Sciences', 'pais': 'EUA',
        'email': 'medinfo@gilead.com', 'cargo': 'Medical Information',
        'tipo_email': 'MedInfo — não BD direto',
        'fonte': 'Domínio gilead.com verificado — empresa Nasdaq',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'Parexel International', 'pais': 'EUA',
        'email': 'lori.dorer@parexel.com', 'cargo': 'SVP Corporate Communications',
        'tipo_email': 'Comunicação corporativa — não BD direto',
        'fonte': 'Encontrado em busca pública de contato Parexel',
        'risco': 'MÉDIO — é Comms, não BD',
    },
    {
        'cat': 'B', 'empresa': 'Amgen Brazil', 'pais': 'EUA',
        'email': 'brazil@amgen.com', 'cargo': 'Brazil Operations',
        'tipo_email': 'Email padrão Brasil',
        'fonte': 'Domínio amgen.com verificado — empresa Nasdaq',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'GSK Brazil', 'pais': 'UK',
        'email': 'br.gsk@gsk.com', 'cargo': 'Brazil Operations',
        'tipo_email': 'Email padrão Brasil',
        'fonte': 'Domínio gsk.com verificado — empresa LSE/NYSE',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'Biocon Biologics', 'pais': 'Índia',
        'email': 'contact@bioconbiologics.com', 'cargo': 'Contact',
        'tipo_email': 'Email geral',
        'fonte': 'Domínio bioconbiologics.com verificado — empresa BSE',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'Teva Pharmaceutical', 'pais': 'Israel',
        'email': 'tevacs@tevapharm.com', 'cargo': 'Customer Service',
        'tipo_email': 'Customer Service — não BD direto',
        'fonte': 'Domínio tevapharm.com verificado — empresa NYSE',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'Zai Lab', 'pais': 'China/EUA',
        'email': 'medinfo@zailaboratory.com', 'cargo': 'Medical Information',
        'tipo_email': 'MedInfo — não BD direto',
        'fonte': 'Domínio zailaboratory.com verificado — empresa Nasdaq',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'BeiGene', 'pais': 'China/EUA',
        'email': 'medicalinformation@beigene.com', 'cargo': 'Medical Information',
        'tipo_email': 'MedInfo — não BD direto',
        'fonte': 'Domínio beigene.com verificado — empresa Nasdaq',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'Eurofarma', 'pais': 'Brasil',
        'email': 'contato@eurofarma.com.br', 'cargo': 'Contato geral',
        'tipo_email': 'Email geral',
        'fonte': 'Domínio eurofarma.com.br verificado',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'EMS Pharma', 'pais': 'Brasil',
        'email': 'contato@ems.com.br', 'cargo': 'Contato geral',
        'tipo_email': 'Email geral',
        'fonte': 'Domínio ems.com.br verificado',
        'risco': 'MÉDIO',
    },
    {
        'cat': 'B', 'empresa': 'Blau Farmacêutica', 'pais': 'Brasil',
        'email': 'ri@blau.com.br', 'cargo': 'Relações com Investidores',
        'tipo_email': 'RI — não comercial direto',
        'fonte': 'Empresa listada B3 — BLAU3',
        'risco': 'MÉDIO — RI pode não chegar ao decisor comercial',
    },

    # ── CATEGORIA C — Bloqueado ───────────────────────────────────────────────
    {
        'cat': 'C', 'empresa': 'Takeda (CONFLITO)', 'pais': 'Japão',
        'email': 'medinfo@takeda.com',
        'motivo': 'CONFLITO — outros emails Takeda (ir@takeda.com e takeda-brazil@takeda.com) bouncearam. Manter bloqueado até obter email verificado de fonte direta.',
    },
    {
        'cat': 'C', 'empresa': 'MSD/Merck Brazil (CONFLITO)', 'pais': 'EUA',
        'email': 'merck@msd.com.br',
        'motivo': 'CONFLITO — latam@merck.com e msd.brasil@merck.com bouncearam anteriormente. Manter bloqueado até verificação individual.',
    },
    {
        'cat': 'C', 'empresa': 'Lonza Group (DUPLICADO — manter apenas Lonza Brazil)', 'pais': 'Suíça',
        'email': 'info@lonza.com',
        'motivo': 'DUPLICADO com contact@lonza.com (Lonza Brazil). Manter apenas um.',
    },
    {
        'cat': 'C', 'empresa': 'Shire/Takeda Ireland', 'pais': 'Irlanda',
        'email': 'medinfo@shire.com',
        'motivo': 'Shire foi adquirida pela Takeda em 2019. Email pode estar inativo. Verificar antes de usar.',
    },
    {
        'cat': 'C', 'empresa': 'Merck KGaA Germany', 'pais': 'Alemanha',
        'email': 'info@merckgroup.com',
        'motivo': 'Email geral sem confirmação de chegada ao BD. Baixa probabilidade de conversão.',
    },
    {
        'cat': 'C', 'empresa': 'Roche Brazil', 'pais': 'Suíça',
        'email': 'brasil.foundation@roche.com',
        'motivo': 'Email de fundação — não comercial. corporate.communications@roche.com bounceou anteriormente.',
    },
    {
        'cat': 'C', 'empresa': 'Novartis Brazil', 'pais': 'Suíça',
        'email': 'media.relations@novartis.com',
        'motivo': 'Email de mídia — não BD. Verificar contato comercial direto antes de usar.',
    },
    {
        'cat': 'C', 'empresa': 'BMS Brazil', 'pais': 'EUA',
        'email': 'bms.medinfo.brasil@bms.com',
        'motivo': 'bms.brazil@bms.com bounceou anteriormente. MedInfo Brasil pode ter mesmo problema.',
    },
]

# Gera relatório
print('=' * 70)
print('LISTA PILOTO FINAL — PARA APROVAÇÃO DO ACIONISTA')
print(f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}')
print('NENHUM DISPARO ATIVO — AGUARDANDO APROVAÇÃO EXPRESSA')
print('=' * 70)

cat_a = [l for l in LEADS if l['cat'] == 'A']
cat_b = [l for l in LEADS if l['cat'] == 'B']
cat_c = [l for l in LEADS if l['cat'] == 'C']

print(f'\nCATEGORIA A (Alta segurança): {len(cat_a)} leads')
print(f'CATEGORIA B (Média segurança): {len(cat_b)} leads')
print(f'CATEGORIA C (Bloqueado):       {len(cat_c)} leads')

print(f'\n{"=" * 70}')
print(f'CATEGORIA A — LISTA PILOTO ({len(cat_a)} leads) — Proposta para aprovação')
print('=' * 70)
for i, l in enumerate(cat_a, 1):
    print(f'\n[{i:02d}] {l["empresa"]} | {l["pais"]}')
    print(f'     Cargo:    {l.get("cargo","")}')
    print(f'     E-mail:   {l["email"]}')
    print(f'     Tipo:     {l["tipo_email"]}')
    print(f'     Fonte:    {l["fonte"]}')
    if l.get('reuniao'): print(f'     Reunião:  {l["reuniao"]}')
    print(f'     Risco:    {l.get("risco","")}')

print(f'\n{"=" * 70}')
print(f'CATEGORIA B — BLOQUEADA ATÉ APROVAÇÃO ESPECÍFICA ({len(cat_b)} leads)')
print('=' * 70)
for i, l in enumerate(cat_b, 1):
    print(f'[{i:02d}] {l["empresa"]} <{l["email"]}> — {l["tipo_email"]}')

print(f'\n{"=" * 70}')
print(f'CATEGORIA C — BLOQUEADOS ({len(cat_c)} leads)')
print('=' * 70)
for i, l in enumerate(cat_c, 1):
    print(f'\n[{i:02d}] {l["empresa"]}')
    print(f'     E-mail: {l["email"]}')
    print(f'     Motivo: {l["motivo"]}')

print(f'\n{"=" * 70}')
print('AGUARDANDO APROVAÇÃO DO ACIONISTA')
print('Categoria A aprovada? → Retomar campanha apenas com os 15 leads A')
print('Categoria B aprovada? → Retomar após validação adicional')
print('Categoria C → Manter bloqueada até resolução dos conflitos')
print('=' * 70)
