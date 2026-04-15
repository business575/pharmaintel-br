#Requires -Version 5.0
$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "PharmaIntel BR"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Titulo {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║   PharmaIntel BR  —  Setup Automatico        ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Ok($m)   { Write-Host "  [OK] " -ForegroundColor Green  -NoNewline; Write-Host $m }
function Info($m) { Write-Host "  [..] " -ForegroundColor Yellow -NoNewline; Write-Host $m }
function Erro($m) { Write-Host "  [!!] " -ForegroundColor Red    -NoNewline; Write-Host $m }
function Sep      { Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray }

Titulo

# ── Pasta certa? ────────────────────────────────────────────────────
if (-not (Test-Path "app.py")) {
    Erro "Execute dentro da pasta PharmaIntelBR (onde esta o app.py)"
    Write-Host ""
    Write-Host "  Como fazer:" -ForegroundColor Yellow
    Write-Host "  1. Extraia o ZIP"
    Write-Host "  2. Abra a pasta PharmaIntelBR"
    Write-Host "  3. Clique com botao direito no SETUP.ps1"
    Write-Host "  4. Selecione 'Executar com PowerShell'"
    Read-Host "`n  ENTER para sair"
    exit 1
}

Ok "Pasta: $(Get-Location)"
Write-Host ""

# ── Politica de execucao (corrige o erro que voce viu) ──────────────
Sep
Info "Configurando politica de execucao do PowerShell..."
try {
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force -ErrorAction Stop
    Ok "Politica configurada"
} catch {
    Info "Nao foi possivel alterar a politica — continuando mesmo assim"
}
Write-Host ""

# ── Python ──────────────────────────────────────────────────────────
Sep
Info "Verificando Python..."

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match "Python 3") { $pythonCmd = $cmd; break }
    } catch {}
}

if (-not $pythonCmd) {
    Erro "Python nao encontrado"
    Write-Host ""
    Write-Host "  Tentando instalar via winget..." -ForegroundColor Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements --silent
        $pythonCmd = "python"
        Ok "Python instalado via winget"
    } else {
        Write-Host ""
        Write-Host "  Abra este link, instale o Python e execute novamente:" -ForegroundColor Yellow
        Write-Host "  https://python.org/downloads" -ForegroundColor Cyan
        Start-Process "https://www.python.org/downloads/"
        Read-Host "`n  ENTER para sair"
        exit 1
    }
} else {
    $ver = & $pythonCmd --version 2>&1
    Ok "$ver"
}
Write-Host ""

# ── pip ─────────────────────────────────────────────────────────────
Sep
Info "Atualizando pip..."
& $pythonCmd -m pip install --upgrade pip --quiet 2>&1 | Out-Null
Ok "pip ok"
Write-Host ""

# ── Dependencias ────────────────────────────────────────────────────
Sep
Info "Instalando dependencias..."
Write-Host ""

$pkgs = @("streamlit","plotly","pandas","numpy","pyarrow","tenacity","requests","groq","python-dotenv","loguru")
$n = 0
foreach ($p in $pkgs) {
    $n++
    Write-Host "    [$n/$($pkgs.Count)] $p" -ForegroundColor Gray
    & $pythonCmd -m pip install $p --quiet 2>&1 | Out-Null
}

Write-Host ""
Ok "Todas as dependencias instaladas"
Write-Host ""

# ── .env ────────────────────────────────────────────────────────────
Sep
if (-not (Test-Path ".env")) {
    Info "Configurando .env..."
    Write-Host ""
    Write-Host "  Chave do Agente IA (gratis em console.groq.com)" -ForegroundColor White
    Write-Host "  Pressione ENTER para pular e usar modo demo" -ForegroundColor DarkGray
    Write-Host ""
    $key = Read-Host "  GROQ_API_KEY"
    if ([string]::IsNullOrWhiteSpace($key)) {
        "APP_ENV=development" | Out-File ".env" -Encoding UTF8
        Info "Sem chave Groq — rodando em modo demo"
    } else {
        @("APP_ENV=development","GROQ_API_KEY=$key") | Out-File ".env" -Encoding UTF8
        Ok "GROQ_API_KEY salva"
    }
} else {
    Ok ".env ja existe"
}
Write-Host ""

# ── Pastas ──────────────────────────────────────────────────────────
Sep
Info "Criando pastas..."
@("data\raw","data\processed","data\exports") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}
Ok "Estrutura de pastas ok"
Write-Host ""

# ── ETL opcional ────────────────────────────────────────────────────
Sep
Write-Host ""
Write-Host "  Baixar dados reais? (Comex Stat + ANVISA ~200MB)" -ForegroundColor White
Write-Host "  S = sim, baixar agora   N = pular, usar modo demo" -ForegroundColor DarkGray
Write-Host ""
$etl = Read-Host "  [s/N]"
if ($etl -match "^[sS]$") {
    Write-Host ""
    Info "Executando ETL 2024 — aguarde..."
    Write-Host ""
    try {
        & $pythonCmd -m src.utils.etl_pipeline 2024
        Ok "Dados reais carregados!"
    } catch {
        Info "ETL encontrou erro — dashboard abre em modo demo mesmo assim"
    }
}

# ── Launch ──────────────────────────────────────────────────────────
Write-Host ""
Sep
Write-Host ""
Ok "Setup concluido!"
Write-Host ""
Write-Host "  Abrindo dashboard em http://localhost:8501" -ForegroundColor Cyan
Write-Host "  Para encerrar: feche esta janela" -ForegroundColor DarkGray
Write-Host ""
Sep
Write-Host ""

Start-Job { Start-Sleep 3; Start-Process "http://localhost:8501" } | Out-Null
& $pythonCmd -m streamlit run app.py --server.headless false --browser.gatherUsageStats false
