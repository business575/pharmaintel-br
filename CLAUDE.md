# PharmaIntel BR — Memória do Projeto para Claude Code

## Visão Geral

**PharmaIntel BR** é uma plataforma SaaS B2B de inteligência de mercado farmacêutico brasileiro.  
Ela integra dados públicos de múltiplas fontes governamentais para gerar insights estratégicos para importadores de medicamentos e dispositivos médicos no Brasil.

---

## Problema que Resolve

O Brasil possui mais de **8.500 importadores ativos** de produtos farmacêuticos e dispositivos médicos.  
Esses importadores enfrentam dificuldades para:
- Monitorar o desempenho do mercado em tempo real
- Identificar concorrentes e oportunidades por NCM
- Navegar pela complexidade regulatória da ANVISA
- Rastrear licitações e compras públicas (ComprasNet)

---

## Fontes de Dados Integradas

| Fonte        | Descrição                                              | Cobertura             |
|--------------|--------------------------------------------------------|-----------------------|
| **Comex Stat** (MDIC) | Dados de importação/exportação por NCM, país, empresa | Capítulos 30 e 90 da TEC |
| **BPS**      | Balança de Pagamentos de Serviços (Banco Central)     | Remessas e royalties farmacêuticos |
| **ANVISA**   | Registros de produtos, alertas sanitários, regularidade | Medicamentos e dispositivos |
| **ComprasNet** | Licitações e contratos públicos federais             | Compras governamentais |

### NCMs Principais
- **Capítulo 30**: Medicamentos, vacinas, reagentes diagnósticos
- **Capítulo 90**: Dispositivos médicos, equipamentos de diagnóstico

---

## Stack Tecnológica

```
Backend / Processamento
  - Python 3.11+
  - Pandas / Polars     → ETL e análise de dados
  - Requests / HTTPX    → Consumo de APIs públicas

Frontend / Dashboard
  - Streamlit           → Interface web principal
  - Plotly / Altair     → Visualizações interativas

Agente de IA
  - Groq API (Llama 3.3 70B)  → Análise estratégica e geração de insights
  - LangChain / LangGraph     → Orquestração do agente

Infraestrutura
  - GitHub (ViniciusGHA)      → Controle de versão
  - .env                      → Variáveis de ambiente (nunca commitar)
```

---

## Estrutura de Pastas

```
PharmaIntelBR/
│
├── data/
│   ├── raw/           → Dados brutos baixados das APIs públicas
│   ├── processed/     → Dados limpos e transformados
│   └── exports/       → Relatórios e exports para o usuário
│
├── src/
│   ├── agents/        → Agente de IA (Groq/Llama) e lógica de raciocínio
│   ├── integrations/  → Conectores para Comex Stat, ANVISA, BPS, ComprasNet
│   └── utils/         → Funções auxiliares, formatação, helpers
│
├── dashboard/
│   ├── components/    → Componentes Streamlit reutilizáveis
│   └── assets/        → Imagens, logos, CSS customizado
│
├── docs/              → Documentação técnica e de negócio
│
├── CLAUDE.md          → Este arquivo — memória do projeto para Claude Code
├── .env               → Chaves de API (NÃO commitar no Git)
├── .gitignore         → Ignorar .env, __pycache__, data/raw/, etc.
└── requirements.txt   → Dependências Python
```

---

## Modelo de Negócio

**Público-alvo**: Importadores farmacêuticos brasileiros (CNPJ ativos com histórico Comex Stat)

**Planos de assinatura** (proposto):
| Plano     | Preço/mês | Recursos                                      |
|-----------|-----------|-----------------------------------------------|
| Starter   | R$ 297    | Dashboard básico, 3 NCMs monitorados          |
| Pro       | R$ 697    | Todos NCMs, alertas ANVISA, ComprasNet        |
| Enterprise| R$ 1.497  | API access, white-label, suporte dedicado     |

---

## Convenções de Código

- Todos os arquivos Python em `src/` devem ter docstrings
- Variáveis de ambiente carregadas via `python-dotenv`
- Nunca hardcodar API keys — usar sempre `.env`
- Commits em português ou inglês, mas consistentes por PR
- Logs com `loguru` (preferido sobre `logging` padrão)

---

## Status Atual

- [x] Definição da arquitetura e fontes de dados
- [x] Estrutura de pastas criada
- [x] CLAUDE.md criado
- [ ] Conectores das APIs públicas (Comex Stat, ANVISA)
- [ ] Pipeline ETL inicial (Capítulo 30)
- [ ] Dashboard MVP (Streamlit)
- [ ] Integração do Agente IA (Groq)
- [ ] Autenticação e sistema de assinaturas

---

## Notas Importantes para o Agente (Claude Code)

1. **Segurança**: Nunca incluir API keys ou tokens em código ou outputs
2. **Dados sensíveis**: Arquivos em `data/raw/` podem conter dados de empresas — não logar CNPJs em produção
3. **Rate limits**: APIs do MDIC e ANVISA têm limites — implementar retry com backoff exponencial
4. **Encoding**: Dados brasileiros frequentemente em ISO-8859-1 — sempre converter para UTF-8 no ETL
5. **Datas**: Formato brasileiro DD/MM/AAAA nas APIs — normalizar para ISO 8601 internamente
