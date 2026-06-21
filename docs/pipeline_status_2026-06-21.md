# PIPELINE DE VENDAS — Status Verificado
**Data:** 21/06/2026 (domingo)
**Agente:** CEO AI / Autonomous Sales Agent
**Branch:** claude/peaceful-curie-yni98d

> Todos os sinais abaixo foram extraídos do inbox Gmail, Google Calendar e arquivos do projeto.
> Nada inventado. Cada item tem fonte documentada.

---

## 1. REVENUE STATUS

| Métrica | Valor | Fonte |
|---|---|---|
| Pagamentos Stripe (30d) | **R$ 0** | Inbox Gmail — nenhum recibo `from:stripe.com` |
| Assinaturas ativas (DB) | **0** | `data/pharmaintel.db` → tabela `users` (1 admin, 0 subscriptions) |
| Bookings Calendly | **0** | Inbox Gmail — nenhum email `from:calendly.com` |
| MRR atual | **R$ 0** | Sem clientes pagantes verificáveis |

**Conclusão:** Nenhuma receita PharmaIntel reconhecida nos últimos 30 dias.

---

## 2. OPORTUNIDADE QUENTE #1 — A.C. CAMARGO CANCER CENTER

**Status:** 🔥 DEMO ENTERPRISE AGENDADA

| Campo | Valor |
|---|---|
| Data/Hora | **Sexta-feira 26/06/2026, 14:30-15:20 (BRT)** |
| Local | Microsoft Teams |
| Link | https://teams.live.com/meet/93795783071917?p=uUk7p5aYRlxOZCirMS |
| Participantes A.C. Camargo | Eliana Morgante (Gerente Mat. e Medicamentos)<br>Willian Machado (Gerente Suprimentos)<br>Aline Rezende (Especialista Farmácia) — ACEITOU<br>Bruna Lima Cardoso — ACEITOU |
| Pauta confirmada | Mapa Fornecedores (trastuzumabe, pembrolizumabe, bevacizumabe, rituximabe) · Business Score Economicidade · Calculadora Preço Aterrissagem · Clinical Trials PubMed · **Proposta comercial Enterprise** |
| Lead status auditoria | VERIFICADO (`auditoria_base.py` — "accamargo.org.br — hospital verificado, inbound confirmado") |
| Ticket potencial | Enterprise R$ 4.997/mês (~R$ 60k ARR) |
| Probabilidade qualitativa | ALTA — inbound + demo Enterprise marcada + 4 stakeholders engajados |

**Próxima ação (Vinicius):**
1. Validar dados antes da demo: rodar `python scripts/validar_dados.py` (CMED: trastuzumabe < pembrolizumabe).
2. Preparar slides Mapa Fornecedores específicos para os 4 oncológicos da pauta.
3. Calcular Business Score real para os NCMs oncológicos do A.C. Camargo.
4. Trazer 1 slide com proposta Enterprise (R$ 4.997/mês) e ROI vs. economia em compras.

**RISCO:** Sem preparação, demo Enterprise vira call genérica → perde a maior oportunidade do trimestre.

---

## 3. SINAL #2 — PREGÃO ELETRÔNICO MEDICAMENTOS (DEADLINE 25/06)

**Status:** ⏰ PRAZO EM 4 DIAS

| Campo | Valor |
|---|---|
| Origem | smscla.mandadojudicial04@gmail.com (Secretaria Municipal de Saúde) |
| Processo | SMS-PRO-2025/41550 — ESTIMATIVA DE PREÇO |
| Recebido em | 18/06/2026 |
| **Deadline** | **25/06/2026 às 18:00** |
| Objeto | Aquisição de medicamentos (Lei 14.133/21, Art. 28, Inciso I) |
| Anexos | "PEDIDO DE COTAÇÃO 41550.xlsx" + "TR.pdf" (Termo de Referência) |
| Forma de resposta | E-mail com proposta assinada, validade 180 dias |

**Decisão pendente (Vinicius):**
- A GHA/PharmaIntel atuam como SaaS/consultoria, não como distribuidor de medicamentos.
- Opções: (a) responder negativamente educadamente; (b) repassar para parceiro distribuidor e cobrar fee; (c) abrir os anexos e avaliar se algum item da TR cabe no perfil de fornecimento da GHA.
- **Não tomei ação** porque a regra exige aprovação manual.

---

## 4. SINAL #3 — PIPELINE HOSPITALAR 2026 ESFRIANDO

**Status:** ⚠️ JANELA PÓS-EVENTO FECHANDO

| Métrica | Valor |
|---|---|
| Leads verificados (CSV) | 20 empresas (`hospitalar_2026_leads.csv`) |
| Fit ALTO | 13 |
| Fit MÉDIO | 7 |
| Data do evento | 19-22 maio 2026 (há 30 dias) |
| Contatos realizados | **0 de 20** (todos com `status = "não contatado"`) |
| Bloqueio | Cada lead marcado "Aguardar aprovação manual antes de contato" |

**Top 5 prioritárias parados:**
1. Breas Medical (Suécia) — Ventilação mecânica
2. Cormay Diagnostics (Polônia) — IVD
3. Endiatx (EUA) — Cápsula endoscópica robótica
4. Grupo Vera Rosas (Brasil) — Consultoria reg., parceiro canal
5. Swisslog Healthcare (Suíça) — Automação farmácia hospitalar

**Recomendação:** Liberar lote de envio nos próximos 7 dias antes do efeito "calor pós-feira" sumir.
**Ação necessária:** Aprovação explícita do Vinicius por empresa (templates A/B/C já prontos em `hospitalar_2026_resumo.md`).

---

## 5. SINAL #4 — FRESENIUS MEDICAL CARE (RENDA PARALELA)

**Status:** 📅 ENTREVISTA TEAMS AGENDADA

| Campo | Valor |
|---|---|
| Contato | Carla Fritsch <carla.fritsch@freseniusmedicalcare.com> |
| Posição | Gerente de Market Access — Brasil |
| Faixa salarial negociada | R$ 22.000 – R$ 28.000 (já discutida via email) |
| Convite Teams | ID 289 807 331 733 195 · Senha: aU3sM738 |
| Última troca | 16/06/2026 (Vinicius enviou contraproposta) |

**Observação:** Este é processo seletivo de emprego, não venda PharmaIntel. Pode ser fonte de fluxo de caixa paralelo enquanto o SaaS escala.

**Cuidado detectado:** Em 17/06 Vinicius tentou encaminhar o convite Teams para `vinicius.hospitalar@gmail.comv` (typo — domínio inexistente). Cópia correta foi enviada para business@globalhealthcareaccess.com. Sem perda real, mas confirma falha de digitação.

---

## 6. AUTONOMOUS SALES AGENT — STATUS

| Item | Estado |
|---|---|
| `src/agents/autonomous_sales_agent.py` | Existe, código pronto |
| `data/exports/auto_sales_leads.csv` | **Não existe** — agente nunca rodou |
| `data/demo_leads.json` | `[]` vazio |
| Provedores configurados | Brevo (primário) ou Resend (fallback) — não testados nesta sessão |
| Bloqueio para execução | Regra de ouro: validação `auditoria_base.py` + `validar_dados.py` (paths Windows hardcoded — não rodam neste container Linux) |

**Não rodei o agente nesta sessão.** Justificativa:
- Scripts de validação têm `os.chdir('C:/Users/vinic/OneDrive/Desktop/...')` que falham aqui.
- Sem validação prévia, enviar emails viola a Regra de Ouro.
- Mandato CEO: "Cannot send messages without approval."

---

## 7. DECISÕES NECESSÁRIAS DO VINICIUS

| # | Decisão | Prazo | Impacto |
|---|---|---|---|
| 1 | Confirmar agenda de preparo da demo A.C. Camargo (esta semana) | Antes de 26/06 | Maior ticket do trimestre |
| 2 | Responder ao Pregão SMS-CLA: cotar, declinar ou repassar | 25/06 18h | Pode abrir caminho municipal |
| 3 | Aprovar lote de outreach Hospitalar 2026 (Top 5) | Esta semana | Salva o pipeline da feira |
| 4 | Confirmar/adiar data da entrevista Fresenius | Conforme convite Teams | Renda paralela |
| 5 | Portar `validar_dados.py` e `auditoria_base.py` para Linux (path relativo) | Antes de qualquer envio | Habilita automação |

---

## 8. AÇÃO ÚNICA E IMEDIATA

**Single next action:** Bloquear 2 horas de preparação para a demo Enterprise A.C. Camargo na quinta-feira 25/06, com slide-deck específico em trastuzumabe/pembrolizumabe/bevacizumabe/rituximabe e proposta Enterprise R$ 4.997/mês pronta para apresentar.
