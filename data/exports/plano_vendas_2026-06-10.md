# Plano de Vendas — 10/06/2026
## PharmaIntel BR / GlobalAccess.AI — CEO AI

**Status:** Nenhum contato enviado. Nenhuma automação ativa. Aguardando decisões do acionista.
**Branch:** `claude/peaceful-curie-c1e08b`

---

## 1. Diagnóstico Honesto do Estado Atual

### 1.1 O que existe e é verificável

| Ativo | Estado | Fonte |
|---|---|---|
| Lista verificada de empresas globais (44) | Pronta | `scripts/auditoria_base.py` (VERIFIED_COMPANIES) |
| Top 20 Hospitalar 2026 (mapeamento comercial) | Pronta — fontes documentadas | `data/exports/hospitalar_2026_leads.csv` |
| Top 7 com mensagens aprovadas pelo acionista | Pronta — template aprovado em 13/05 | `data/exports/hospitalar_2026_top7_strategy.md` |
| Produtos Stripe em produção (BRL) | Configurados e cobráveis | `stripe_products.py` |
| Plataforma PharmaIntel (dashboard + dados ANVISA/Comex/CMED) | Operacional | `app.py`, `data/processed/*` |

### 1.2 Bloqueios reais para execução autônoma neste container

1. **Scripts críticos com paths Windows hardcoded** — `scripts/auditoria_base.py` e `scripts/validar_dados.py` apontam para `C:/Users/vinic/OneDrive/Desktop/PharmaIntelBR`. Não executam em container Linux. Precisam ser portados (substituir por `Path(__file__).resolve().parent.parent`).
2. **`.env` ausente** — só existe `.env.example`. Sem Groq, sem Gmail SMTP, sem Stripe live key, sem DB credenciais.
3. **`data/demo_leads.json` vazio** (`[]`).
4. **Sem inbound de respostas para triar** — a Etapa 2 do briefing (QUENTE/MORNO/FRIO) não tem matéria-prima.
5. **Sem `gh` CLI / SMTP / API Gmail neste ambiente** — qualquer envio precisa ser manual pelo Vinicius ou via Gmail MCP (drafts, não envios diretos).

> **Conclusão:** "Executar o agente de prospecção" como atividade autônoma neste container é **infactível hoje**. O que é factível é entregar artefatos prontos para o Vinicius aprovar e disparar (LinkedIn + email manual ou via Gmail MCP draft).

---

## 2. Decisões Requeridas do Acionista (BLOQUEANTES)

Sem essas três decisões, **qualquer envio é risco** (pode comprometer credibilidade ou gerar cobrança errada).

### 2.1 Tabela de preços — 3 fontes divergentes

| Fonte | Starter/mês | Pro/mês | Enterprise/mês |
|---|---|---|---|
| Briefing 10/06/2026 (este pedido) | R$ 997 | R$ 2.497 | R$ 4.997 |
| `CLAUDE.md` (memória do projeto) | R$ 297 | R$ 697 | R$ 1.497 |
| **Stripe em produção** (`stripe_products.py`) | **R$ 299** | **R$ 699** | **R$ 1.599** |

> Hoje, o cliente que clicar no checkout paga **R$ 299 / 699 / 1.599** — é o único preço cobrável.
> Mencionar R$ 997 / 2.497 / 4.997 em propostas sem atualizar Stripe = quebra de promessa no fechamento.
>
> **Decisão pedida:** qual tabela vale? Se for a nova (R$ 997+), preciso de OK para atualizar `stripe_products.py` e CLAUDE.md antes de qualquer oferta.

### 2.2 Brand e URL pública

| Fonte | Brand | URL | Email |
|---|---|---|---|
| Briefing de hoje | "PharmaIntel BR" | `https://pharmaceuticaai.com` | `business@globalhealthcareaccess.com` |
| Materiais existentes | "PharmaIntelBR / GlobalAccess.AI" | (não há landing pública confirmada) | `business@globalhealthcareaccess.com` |
| Repo | `pharmaintel-br` | `index.html`, `tour-pt.html` locais | — |

> **Decisão pedida:** `pharmaceuticaai.com` está no ar e estável? Posso usar nas mensagens? Hoje vou usar o link só após confirmação.

### 2.3 Contas estratégicas — verificação de fonte

| Empresa | Status na base | Fonte | Pronto para abordagem? |
|---|---|---|---|
| Oncoclínicas | VERIFICADO | `grupooncoclinicas.com` — B3 listada | Sim (com aprovação) |
| DASA | VERIFICADO | `dasa.com.br` — B3 listada | Sim (com aprovação) |
| Rede D'Or | VERIFICADO | `rededorsaoluiz.com.br` — B3 listada | Sim (com aprovação) |
| Fleury | **NÃO está na base** | A verificar (B3: `fleury.com.br`) | **Não — adicionar à VERIFIED_COMPANIES com fonte primeiro** |
| Kora Saúde | **NÃO está na base** | A verificar (`korasaude.com.br`) | **Não — adicionar à VERIFIED_COMPANIES com fonte primeiro** |

> **Regra de Ouro:** lead sem fonte = risco. Nenhuma mensagem para Fleury ou Kora até atualizar a auditoria.

---

## 3. Abordagem Personalizada — 3 Contas Verificadas

> **Princípio:** primeiro gerar valor, depois conduzir para reunião. Sem pitch direto. Sem preço.
> **Status:** drafts. Nenhum envio. Aprovação manual obrigatória.

### 3.1 Oncoclínicas (B3: ONCO3) — Foco: oncológicos e licitações

**Por que agora (ângulo de valor real):**
- A PharmaIntel cruza Comex Stat (Cap. 30) + ANVISA + CMED para os principais oncológicos (trastuzumabe, pembrolizumabe, bevacizumabe, rituximabe — todos já validados em `validar_dados.py`).
- Oncoclínicas tem rede própria de 100+ unidades — compra oncológicos de alto custo e participa de licitações SUS/operadoras.
- Inteligência sobre quem importa, quanto importa, preço FOB médio e fornecedor por molécula = vantagem direta em negociação com fabricante e em PEC.

**Conteúdo gerador de valor (não-pitch) — entregar antes de pedir reunião:**
> Snapshot 1 página: "Importações de pembrolizumabe e trastuzumabe no Brasil — Jan-Mai/2026 vs 2025" (extraível de `pharma_imports_2026.parquet`).

**Mensagem LinkedIn — Diretor de Suprimentos / CFO** *(precisa de aprovação do Vinicius)*:
```
Olá [Nome],

Acabei de rodar um cruzamento de Comex Stat + CMED para os top
oncológicos importados no Brasil em 2026 — pembrolizumabe e
trastuzumabe lideram em valor. Vi alguns movimentos de fornecedor
nos últimos 90 dias que podem impactar negociação direta.

Posso te mandar a página com os dados (sem custo, sem pitch)?

Vinicius Figueiredo | PharmaIntel BR
```

**Próxima ação se responder:** enviar snapshot → no follow-up oferecer 20 min para mostrar como o monitoramento contínuo se traduz em ganho de margem.

---

### 3.2 DASA (B3: DASA3) — Foco: reagentes IVD e inteligência de fornecedor

**Por que agora:**
- DASA é a maior rede diagnóstica do Brasil — compra volumes altos de reagentes IVD (Cap. 30 + 90).
- A PharmaIntel tem dados ANVISA IVD em `anvisa_dispositivos.parquet` + import data por NCM.
- Movimentos recentes (Cormay Diagnostics no pavilhão polonês na Hospitalar) sugerem novos entrantes — saber quem entra antes do concorrente importa.

**Conteúdo gerador de valor:**
> "Top 10 fornecedores estrangeiros de reagentes IVD que entraram no Brasil em 2026 — com volume FOB e status ANVISA."

**Mensagem LinkedIn — Diretor de Compras / Supply Chain**:
```
Olá [Nome],

Mapeei os novos fornecedores estrangeiros de reagentes IVD que
entraram no Brasil em 2026 (dados Comex + ANVISA cruzados).
Alguns players novos que ainda não estão no radar das grandes redes.

Posso te enviar o mapa (1 página, sem custo)?

Vinicius Figueiredo | PharmaIntel BR
```

---

### 3.3 Rede D'Or (B3: RDOR3) — Foco: dispositivos médicos e supply hospitalar

**Por que agora:**
- Rede D'Or = maior rede hospitalar privada do Brasil. Cap. 90 (dispositivos médicos) é o seu core de compra.
- A PharmaIntel tem o link `ncm_empresa_link.parquet` + ANVISA dispositivos — consigo dizer quais importadores trazem cada NCM e a preço médio.
- Em paralelo, o mapeamento Hospitalar 2026 identificou Swisslog Healthcare (automação de farmácia hospitalar) como fit direto — pode virar pauta de conversa.

**Conteúdo gerador de valor:**
> "Importação de dispositivos médicos de alto custo no Brasil 2026 — top 20 NCMs com variação de preço FOB médio YoY."

**Mensagem LinkedIn — Diretor de Suprimentos / Engenharia Clínica**:
```
Olá [Nome],

Rodei um comparativo dos 20 NCMs de dispositivos médicos com maior
variação de preço FOB em 2026 vs 2025. Alguns equipamentos
cirúrgicos com queda de 12-18% que podem virar oportunidade de
renegociação ou novo entrante.

Posso te mandar o resumo (1 página)?

Vinicius Figueiredo | PharmaIntel BR
```

---

## 4. Fleury e Kora — Etapa de Verificação Antes de Abordagem

**Nenhuma mensagem para Fleury ou Kora até concluir:**

1. Adicionar à `VERIFIED_COMPANIES` em `scripts/auditoria_base.py`:
   - Fleury: `fleury.com.br` — empresa listada B3 (`FLRY3`), verificada
   - Kora Saúde: `korasaude.com.br` — empresa listada B3 (`KRSA3`), verificada
2. Rodar `auditoria_base.py` (após portar paths Linux).
3. Identificar contato BD/Compras via LinkedIn — não inventar email.
4. Voltar ao Vinicius com draft só depois de fonte documentada.

---

## 5. Etapa 2 (Tratamento de Respostas) — Sem Matéria-Prima

A Etapa 2 do briefing exige classificar respostas em QUENTE/MORNO/FRIO. **Não há respostas no contexto desta sessão.**

Quando chegarem respostas (Gmail MCP está disponível neste ambiente), o fluxo será:

| Sinal | Classificação | Ação | Link |
|---|---|---|---|
| Pede preço, quer call, pergunta como contratar | QUENTE | Resposta com agenda + link plataforma (após confirmar URL na §2.2) | + Stripe checkout link |
| Pergunta o que fazemos, dúvida regulatória, "depois conversamos" | MORNO | Conteúdo educativo (1 dado concreto da plataforma) + criar urgência leve | snapshot 1 página |
| "Sem interesse", "não é prioridade" | FRIO | Encerrar com nota cordial + reativar em 90 dias | — |

Vou anexar este fluxo aos drafts assim que houver respostas reais para classificar.

---

## 6. Próximas Ações em Ordem

1. **Vinicius decide:** tabela de preços (§2.1), brand/URL (§2.2), Fleury/Kora go/no-go (§2.3).
2. **Eu porto** `auditoria_base.py` e `validar_dados.py` para paths Linux (1 commit pequeno).
3. **Eu rodo** `validar_dados.py` localmente para confirmar integridade dos dados antes de gerar qualquer 1-pager.
4. **Eu gero** os 3 snapshots de 1 página (Oncoclínicas / DASA / Rede D'Or) a partir dos dados em `data/processed/`.
5. **Vinicius aprova** os 3 drafts de LinkedIn e dispara manualmente (ou criamos drafts no Gmail MCP).
6. **Sem envio para Fleury/Kora** até concluir verificação.

---

## 7. Relatório Final (formato CEO Mandate)

1. **Receita status:** Sem receita nova hoje. Nenhum contrato fechado nesta sessão.
2. **Oportunidades ativas:** 7 leads Hospitalar 2026 (Top 7) com template aprovado em 13/05, status de envio desconhecido nesta sessão — precisa de update do Vinicius.
3. **Pipeline value (potencial, NÃO confirmado):** 3 contas estratégicas brasileiras com ticket Enterprise (R$ 1.599/mês cobrável hoje → R$ 19.188/ano por conta se fechar todas as três = R$ 57.564/ano ARR potencial). **Isto é potencial, não realizado.**
4. **Closing probability:** indeterminada — nenhuma conversa iniciada com as 3 contas estratégicas brasileiras.
5. **Riscos imediatos:** (a) preços divergentes podem queimar credibilidade no fechamento; (b) URL `pharmaceuticaai.com` não confirmada — não posso usar até OK do acionista; (c) Fleury/Kora não verificados — abordagem agora violaria a Regra de Ouro.
6. **Decisões requeridas:** §2.1, §2.2, §2.3 deste documento.
7. **Ações já preparadas:** este plano + 3 drafts personalizados com ângulo de valor + lista de verificação para Fleury/Kora.
8. **Próxima ação de receita:** alinhar preços (§2.1) — sem isso, qualquer pitch é mentira parcial.
9. **Impacto na meta de BRL 50.000/mês:** as 3 contas estratégicas brasileiras representam ~R$ 4.797/mês se fecharem todas no Enterprise atual (R$ 1.599 × 3) = 9,6% da meta. Insuficiente isolado — precisa combinar com retainers GHA e Top 7 Hospitalar.

---

**Single next action: Vinicius decide qual tabela de preços é oficial (briefing de hoje R$ 997+, CLAUDE.md R$ 297+ ou Stripe atual R$ 299+) — sem isso nada sai.**
