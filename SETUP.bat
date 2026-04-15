@echo off
chcp 65001 >nul
title PharmaIntel BR — Setup e Deploy
color 0A

echo.
echo  ██████╗ ██╗  ██╗ █████╗ ██████╗ ███╗   ███╗ █████╗ 
echo  ██╔══██╗██║  ██║██╔══██╗██╔══██╗████╗ ████║██╔══██╗
echo  ██████╔╝███████║███████║██████╔╝██╔████╔██║███████║
echo  ██╔═══╝ ██╔══██║██╔══██║██╔══██╗██║╚██╔╝██║██╔══██║
echo  ██║     ██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║
echo  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝
echo  Intel BR — Plataforma de Inteligencia Farmaceutica
echo.
echo  ============================================================
echo.

REM ── Verifica se está na pasta certa ─────────────────────────────
if not exist "app.py" (
    echo  [ERRO] Este script deve estar na pasta PharmaIntelBR
    echo         junto com o arquivo app.py
    echo.
    echo  Extraia o ZIP e coloque o SETUP.bat dentro da pasta
    echo  PharmaIntelBR antes de executar.
    echo.
    pause
    exit /b 1
)

REM ── Verifica Python ─────────────────────────────────────────────
echo  [1/5] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Python nao encontrado. Abrindo pagina de download...
    echo.
    echo  INSTRUCOES:
    echo  1. Baixe e instale o Python em: https://python.org/downloads
    echo  2. IMPORTANTE: marque a opcao "Add Python to PATH"
    echo  3. Apos instalar, execute este script novamente
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo      %%i encontrado
echo.

REM ── Atualiza pip ────────────────────────────────────────────────
echo  [2/5] Atualizando pip...
python -m pip install --upgrade pip --quiet
echo      pip atualizado
echo.

REM ── Instala dependencias ────────────────────────────────────────
echo  [3/5] Instalando dependencias (pode demorar 1-2 min)...
echo.

set DEPS=streamlit plotly pandas numpy pyarrow tenacity requests groq python-dotenv loguru

for %%d in (%DEPS%) do (
    echo      Instalando %%d...
    python -m pip install %%d --quiet
)

echo.
echo      Todas as dependencias instaladas!
echo.

REM ── Configura .env ──────────────────────────────────────────────
echo  [4/5] Configurando variaveis de ambiente...

if exist ".env" (
    echo      .env ja existe — mantendo configuracoes atuais
) else (
    echo.
    echo  ┌─────────────────────────────────────────────────┐
    echo  │  GROQ API KEY (para o Agente IA)                │
    echo  │                                                  │
    echo  │  1. Acesse: https://console.groq.com            │
    echo  │  2. Crie uma conta gratuita                     │
    echo  │  3. Gere uma API Key                            │
    echo  │  4. Cole abaixo (ou pressione ENTER para pular) │
    echo  └─────────────────────────────────────────────────┘
    echo.
    set /p GROQ_KEY="  Cole sua GROQ_API_KEY: "

    if "!GROQ_KEY!"=="" (
        echo      Pulando — o dashboard rodara sem o Agente IA
        echo APP_ENV=development> .env
    ) else (
        echo APP_ENV=development> .env
        echo GROQ_API_KEY=!GROQ_KEY!>> .env
        echo      GROQ_API_KEY salva no .env
    )
)
echo.

REM ── Cria pastas necessarias ──────────────────────────────────────
echo  [5/5] Preparando estrutura de pastas...
if not exist "data\raw"       mkdir data\raw
if not exist "data\processed" mkdir data\processed
if not exist "data\exports"   mkdir data\exports
echo      Pastas criadas
echo.

REM ── Pergunta se quer rodar ETL ───────────────────────────────────
echo  ============================================================
echo.
echo  Deseja baixar dados reais agora?
echo  (Comex Stat + ANVISA — pode demorar alguns minutos)
echo.
set /p RUN_ETL="  Baixar dados reais? [s/N]: "

if /i "!RUN_ETL!"=="s" (
    echo.
    echo  Executando ETL — baixando dados de 2024...
    echo  (Nao feche esta janela)
    echo.
    python -m src.utils.etl_pipeline 2024
    if errorlevel 1 (
        echo.
        echo  [AVISO] ETL encontrou erros — o dashboard rodara em modo demo
        echo          Isso e normal na primeira execucao.
    ) else (
        echo.
        echo  Dados reais carregados com sucesso!
    )
    echo.
)

REM ── Lança o dashboard ────────────────────────────────────────────
echo  ============================================================
echo.
echo  Iniciando PharmaIntel BR Dashboard...
echo.
echo  O browser abrira automaticamente em:
echo  http://localhost:8501
echo.
echo  Para encerrar: feche esta janela ou pressione Ctrl+C
echo.
echo  ============================================================
echo.

REM Abre o browser após 3 segundos
start /b cmd /c "timeout /t 3 >nul && start http://localhost:8501"

python -m streamlit run app.py --server.headless false --browser.gatherUsageStats false

pause
