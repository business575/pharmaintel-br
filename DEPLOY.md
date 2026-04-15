# PharmaIntel BR — Guia de Deploy

## Opção 1 — Rodar local no Windows (mais simples)

1. Extraia o ZIP
2. Abra a pasta `PharmaIntelBR`
3. Dê duplo clique em **`INSTALAR.bat`**
4. Siga as instruções na tela
5. O browser abre automaticamente em http://localhost:8501

> Se aparecer "Python não encontrado", o instalador abre python.org automaticamente.
> Instale marcando **"Add Python to PATH"** e execute o `INSTALAR.bat` novamente.

---

## Opção 2 — Publicar online grátis (Streamlit Cloud)

### Passo 1 — GitHub (2 minutos)
1. Acesse https://github.com e crie uma conta (se não tiver)
2. Clique em **New repository** → nome: `pharmaintel-br` → **Create**
3. Clique em **uploading an existing file**
4. Arraste todos os arquivos da pasta `PharmaIntelBR` para lá
5. Clique **Commit changes**

### Passo 2 — Streamlit Cloud (2 minutos)
1. Acesse https://share.streamlit.io
2. Faça login com sua conta GitHub
3. Clique **New app**
4. Selecione o repositório `pharmaintel-br`
5. Main file path: `app.py`
6. Clique em **Advanced settings** → **Secrets** e cole:
   ```toml
   GROQ_API_KEY = "sua_chave_groq_aqui"
   ```
7. Clique **Deploy!**

Sua URL pública será algo como:
```
https://seuusuario-pharmaintel-br-app-xxxx.streamlit.app
```

> Chave Groq gratuita em: https://console.groq.com

---

## Opção 3 — Criar .EXE standalone (sem Python no destino)

> Use isso para distribuir para clientes que não têm Python.

1. Na pasta `PharmaIntelBR`, execute o `INSTALAR.bat` primeiro (precisa ter Python)
2. Após instalado, dê duplo clique em **`BUILD_EXE.bat`**
3. Aguarde 3-5 minutos
4. O executável estará em `dist\PharmaIntelBR\PharmaIntelBR.exe`
5. Copie a pasta inteira `dist\PharmaIntelBR\` para qualquer PC Windows
6. Execute `PharmaIntelBR.exe` — não precisa de Python instalado

---

## Estrutura de arquivos

```
PharmaIntelBR/
├── INSTALAR.bat          ← duplo clique para instalar e rodar
├── SETUP.ps1             ← script de setup completo
├── BUILD_EXE.bat         ← gera .exe standalone
├── app.py                ← dashboard Streamlit
├── requirements.txt      ← dependências Python
├── launcher.py           ← entry point do .exe
├── pharmaintel.spec      ← configuração PyInstaller
├── src/
│   ├── integrations/
│   │   ├── comex_stat.py ← API Comex Stat (MDIC)
│   │   └── anvisa.py     ← Dados abertos ANVISA
│   ├── utils/
│   │   └── etl_pipeline.py ← Pipeline ETL completo
│   └── agents/
│       └── pharma_agent.py ← Agente IA (Groq/Llama)
└── data/
    ├── raw/              ← dados brutos das APIs
    └── processed/        ← tabelas prontas para o dashboard
```

---

## Problemas comuns

| Erro | Solução |
|------|---------|
| `pip não reconhecido` | Use `INSTALAR.bat` em vez do PowerShell direto |
| `python não encontrado` | Instale em python.org marcando "Add to PATH" |
| `Acesso negado ao .env` | Certifique-se de estar na pasta PharmaIntelBR, não em system32 |
| `ExecutionPolicy` | O `INSTALAR.bat` corrige isso automaticamente |
| Dashboard em modo demo | Execute o ETL: `python -m src.utils.etl_pipeline 2024` |
| Agente IA indisponível | Configure `GROQ_API_KEY` no `.env` (chave grátis em console.groq.com) |
