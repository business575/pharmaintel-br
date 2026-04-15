@echo off
chcp 65001 >nul
title PharmaIntel BR — Build EXE

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   PharmaIntel BR — Gerando .EXE              ║
echo  ╚══════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo  [1/3] Instalando PyInstaller...
python -m pip install pyinstaller --quiet
echo  OK

echo  [2/3] Gerando executavel (pode demorar 3-5 min)...
python -m PyInstaller pharmaintel.spec --clean --noconfirm
echo.

if exist "dist\PharmaIntelBR\PharmaIntelBR.exe" (
    echo  [3/3] Executavel gerado com sucesso!
    echo.
    echo  ╔══════════════════════════════════════════════╗
    echo  ║  Arquivo: dist\PharmaIntelBR\PharmaIntelBR.exe ║
    echo  ║  Copie a pasta dist\PharmaIntelBR para       ║
    echo  ║  qualquer computador Windows e execute       ║
    echo  ║  o .exe — nao precisa de Python instalado!   ║
    echo  ╚══════════════════════════════════════════════╝
    explorer dist\PharmaIntelBR
) else (
    echo  [!!] Erro ao gerar executavel. Verifique os logs acima.
)

echo.
pause
