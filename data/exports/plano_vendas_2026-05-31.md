# Plano de Vendas — 31/05/2026

**Autor:** CEO AI · **Aprovador:** Vinicius Figueiredo
**Status:** Aguardando aprovação do acionista — nenhuma mensagem enviada.
**Janela:** Follow-up pós-Hospitalar (D+9) + abertura de contas estratégicas.

---

## 1. Status de Receita (verificado, sem inferência)

| Métrica | Valor | Fonte |
|---|---|---|
| Receita confirmada (MRR pago) | R$ 0 | Stripe: nenhum assinante ativo verificado neste container |
| Contratos assinados | 0 | Sem PDF/assinatura na pasta `data/` |
| Leads contactados pelo agente autônomo | 0 | `data/exports/auto_sales_leads.csv` não existe |
| Leads VERIFICADOS prontos para contato | 20 | `hospitalar_2026_leads.csv` (fonte documentada por linha) |
| Respostas em caixa para tratar | Desconhecido | Sem acesso ao inbox neste ambiente |

**Não há receita confirmada para reportar. Não há resposta de cliente para classificar como QUENTE/MORNO/FRIO sem inventar.**

---

## 2. Bloqueios Operacionais (precisam ser resolvidos antes de qualquer disparo)

| Bloqueio | Impacto | Quem resolve |
|---|---|---|
| `.env` ausente neste container (sem Groq, Brevo, Resend, Gmail) | Agente autônomo não dispara | Vinicius (configurar secrets no ambiente de produção) |
| `validar_dados.py` e `auditoria_base.py` com paths Windows hardcoded (`C:/Users/vinic/...`) | Pipeline de qualidade não roda em CI/Linux | Refatorar para `Path(__file__).resolve().parents[1]` |
| Discrepância de preços: tarefa pede R$ 997/2.497/4.997; CLAUDE.md e `autonomous_sales_agent.py:295` usam R$ 297/697/1.497 | Não posso enviar proposta com preço sem confirmação | **DECISÃO DO VINICIUS** |
| Links Stripe são placeholders (`buy.stripe.com/starter`, `/pro`) em `autonomous_sales_agent.py:36-37` | Lead "QUENTE" não consegue pagar | Substituir pelos IDs reais do Stripe |
| Banco `pharmaintel.db` sem tabela `prospects` | CRM real ainda não inicializado | Rodar `init_db()` em produção |

---

## 3. Pipeline Real (20 leads verificados, pós-Hospitalar D+9)

Base: `data/exports/hospitalar_2026_leads.csv` — 13 ALTO + 7 MÉDIO. Todos status `não contatado`.
Janela definida no próprio plano de Fase 2: "23-30/05 follow-up pós-feira". **Estamos 1 dia atrás do cronograma.**

### Prioridade IMEDIATA (esta semana) — 5 contas
Critério: fit ALTO + maior probabilidade de fechar em 30-90 dias.

| # | Empresa | Plano sugerido | Próxima ação | Owner |
|---|---|---|---|---|
| 1 | Breas Medical (SE) | Enterprise / retainer Market Access | Follow-up pós-workshop 20/05 — perguntar se conversamos | Vinicius |
| 2 | Cormay Diagnostics (PL) | Pro + ANVISA IVD consultoria | Follow-up referenciando Stand H-200 | Vinicius |
| 3 | Grupo Vera Rosas (BR) | **Parceria canal** (não venda) | Reunião proposta de revenue-share | Vinicius |
| 4 | Swisslog Healthcare (CH) | Enterprise (clientes hospitalares) | Email referenciando lançamento Hospitalar | Vinicius |
| 5 | Endiatx (US) | Snapshot USD 1.000-2.500 + ANVISA | Email LinkedIn pós-evento (entry barrier) | Vinicius |

### Prioridade 2ª onda (próximas 2 semanas) — 8 contas
Acro Biotech, Vave Health, Medicatech USA, Norav Medical, Lodox NA, RVDS, QLS Quality, Phelcom.

### Nutrir (sem pressão) — 7 contas
ARTFX, Vasomedical, Nasco, Totvs, Cloudia, Biosat, Biotecno.

---

## 4. Contas Estratégicas — Abordagem Personalizada

> **Aviso de verificação obrigatória antes de qualquer envio:**
> - Oncoclínicas, DASA, Rede D'Or: **VERIFICADAS** em `auditoria_base.py::VERIFIED_COMPANIES`.
> - Fleury, Kora: **NÃO listadas** como verificadas. Antes de qualquer contato, precisamos:
>   1. Confirmar domínio ativo (fleury.com.br, koraoncologia.com.br)
>   2. Identificar contato individual via LinkedIn (não inventar)
>   3. Adicionar à lista `VERIFIED_COMPANIES`
> - Para todas as 5: **não tenho contato individual confirmado** (nome + email pessoal). Rascunhos abaixo usam placeholder `[Nome]` — preencher só após pesquisa LinkedIn.

Princípio aplicado às 5: **gerar valor primeiro, conduzir para reunião, NÃO vender direto.**

---

### 4.1 Oncoclínicas (verificada) — Ângulo: dados oncológicos + licitações

**Ativo a usar:** `data/processed/produtos_vencendo.parquet` (medicamentos oncológicos com patente vencendo) + `bnafar_fetcher.py` + alertas ComprasNet.

**LinkedIn (1ª mensagem — pedir aceite):**
```
Olá [Nome],

Cruzei dados Comex Stat + ANVISA + ComprasNet para a categoria
oncológica e identifiquei 3 movimentos relevantes para a Oncoclínicas
nos últimos 60 dias (importação de biossimilares, licitações federais,
patentes vencendo em 2026-27).

Posso compartilhar o mapa em PDF (gratuito, 4 páginas). Útil?

Vinicius — PharmaIntel BR
```

**Email seguinte (se aceitar):** entregar o PDF de fato (gerado por `report_generator.py` com dados verificados) — **NÃO** pedir reunião no mesmo email. Pedir reunião no email 3, depois que o valor já foi entregue.

**Oferta de fechamento:** Enterprise (R$ 4.997/mês — *confirmar tabela*) + onboarding com dashboard customizado oncológico. ROI: 1 economia em licitação ≥ 12 meses de plataforma.

---

### 4.2 DASA (verificada) — Ângulo: reagentes IVD + market intel diagnóstico

**Ativo a usar:** `anvisa_dispositivos.parquet` (filtro reagentes IVD) + dados de importação dos principais fornecedores de DASA por NCM 3822 (reagentes diagnósticos).

**LinkedIn:**
```
Olá [Nome],

Mapeei as 15 maiores importações de reagentes diagnósticos no Brasil
em 2025-26 (Comex Stat + ANVISA) e cruzei com lead time médio
ANVISA por fabricante.

Útil para benchmark de fornecedores DASA? Posso mandar o resumo
em 1 página, sem pitch.

Vinicius — PharmaIntel BR
```

**Email follow-up:** anexar resumo de 1 página com 3 insights acionáveis (ex: "fornecedor X tem lead time ANVISA 40% maior que mediana — risco de stockout").

**Oferta:** Pro + retainer mensal de inteligência competitiva R$ 4.997.

---

### 4.3 Fleury (NÃO verificada — bloquear até verificação) — Ângulo: ANVISA + importação

**Pré-requisito:** validar `fleury.com.br` + identificar contato Supply/Regulatório. Sem isso, **não enviar**.

**Hipótese de valor:** Fleury opera laboratórios de alta complexidade — importação de reagentes especializados é dor real. Mas qualquer afirmação específica precisa ser checada antes.

**Rascunho LinkedIn (não disparar):**
```
Olá [Nome],

Tenho dados verificáveis de importação ANVISA de reagentes
laboratoriais (Comex Stat + ANVISA, atualizados mensalmente).
Posso compartilhar 3 insights específicos para o portfólio do Fleury,
sem reunião.

Vinicius — PharmaIntel BR
```

**Ação imediata para Vinicius:** validar empresa e adicionar a `VERIFIED_COMPANIES` antes de qualquer envio.

---

### 4.4 Rede D'Or (verificada) — Ângulo: dispositivos médicos

**Ativo a usar:** `anvisa_dispositivos.parquet` + dados de importação NCM Capítulo 90 (equipamentos médicos).

**LinkedIn:**
```
Olá [Nome],

A Rede D'Or compra dispositivos médicos de ~200 fornecedores
distintos. Mapeei os 20 com maior risco regulatório ANVISA
(notificações, recolhimentos, registro vencendo em 2026-27).

Posso enviar a tabela em 1 página. Sem pitch.

Vinicius — PharmaIntel BR
```

**Oferta:** Enterprise + alertas customizados de risco regulatório por fornecedor.

**ROI argumentável:** 1 recolhimento evitado em hospital de grande porte > 24 meses de plataforma.

---

### 4.5 Kora Saúde (NÃO verificada — bloquear até verificação) — Ângulo: oncologia + expansão

**Pré-requisito:** validar domínio + listar como pública (B3: KRSA3) + identificar Diretoria Comercial/Médica.

**Hipótese de valor:** Kora está em consolidação no segmento oncológico — dados de mercado por região ajudam a precificar aquisições e definir mix de tratamento.

**Rascunho (não disparar):** similar a Oncoclínicas, mas com ângulo de expansão geográfica por NCM oncológico.

**Ação imediata:** verificar e listar.

---

## 5. Materiais Genéricos de Vendas (prontos para uso, após decisão de preço)

### 5.1 Objeções → Respostas

| Objeção | Resposta de 1 linha |
|---|---|
| "Já temos consultoria de market access" | A PharmaIntel não substitui consultoria — entrega o dado bruto verificável que sua consultoria precisaria 2 semanas pra montar. |
| "Não temos orçamento" | Te mando 1 relatório gratuito sobre seu portfólio. Se valer, retomamos em 30 dias. |
| "Manda mais info por email" | Mando, mas o que faz diferença é 15 min mostrando 3 insights específicos pra empresa de vocês. Quando? |
| "Caro" (após preço) | ROI esperado: 1 decisão de importação otimizada paga 12 meses. Posso mostrar o número exato pro NCM principal de vocês. |
| "Vou pensar" | Sem problema. Posso te mandar 1 update mensal gratuito até decidirem? |

### 5.2 Pedido de Pagamento (só após interesse validado + preço confirmado)

```
Perfeito, [Nome]. Confirmando:

Plano: [Pro/Enterprise]
Valor: R$ [X]/mês — cancelamento a qualquer momento
Acesso: imediato após pagamento
Onboarding: call de 60 min em até 48h

Link de pagamento: [URL Stripe REAL — substituir placeholder]

Qualquer dúvida me chama direto: +55-21-97282-9820.
```

---

## 6. Decisões que Vinicius precisa tomar HOJE

1. **Tabela de preços vigente:** R$ 997/2.497/4.997 (tarefa) **ou** R$ 297/697/1.497 (CLAUDE.md + código)?
2. **Aprovação para disparar follow-up nos 5 leads da prioridade imediata** (Breas, Cormay, Vera Rosas, Swisslog, Endiatx)?
3. **Aprovação para iniciar verificação** de Fleury e Kora (não envio, só pesquisa)?
4. **Substituir links Stripe placeholders** em `autonomous_sales_agent.py:36-37` pelos IDs reais — sem isso nenhum fechamento se converte em receita.
5. **Configurar `.env` em produção** (Groq, Brevo, Resend) — sem isso o agente autônomo não roda.

---

## 7. Riscos Imediatos

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Janela de follow-up pós-Hospitalar fechando (D+10) | Alta | Disparar follow-up das 5 contas prioritárias em 48h |
| Lead QUENTE chega e não consegue pagar (Stripe broken) | Alta | Substituir placeholders antes de qualquer envio |
| Enviar com tabela de preço errada | Alta | Decisão item 6.1 antes de qualquer disparo |
| Contato com Fleury/Kora sem verificação prévia | Média | Bloqueado até item 6.3 |

---

## 8. Impacto no objetivo R$ 50k/mês

Cenário conservador (próximos 90 dias):
- 5 contatos prioritários × 30% conversão a reunião × 25% conversão a fechamento = ~0,4 vendas (≈ 1 venda)
- 1 × Enterprise (R$ 4.997) = R$ 4.997 MRR → **10% do objetivo**

Para chegar a R$ 50k MRR só com SaaS, precisamos de ~10 Enterprise ou ~20 Pro. **Recomendação:** combinar SaaS com **2-3 Snapshots pagos USD 1k-2,5k** (não-recorrentes) para gerar caixa rápido enquanto o pipeline SaaS amadurece.

---

**Single next action: Vinicius aprova a tabela de preço (item 6.1) e a lista de 5 follow-ups (item 6.2). Sem isso, nada sai daqui.**
