@echo off
:: PharmaIntel BR — Instalador com duplo clique
:: Este arquivo resolve automaticamente o bloqueio de politica do PowerShell

chcp 65001 >nul 2>&1
title PharmaIntel BR — Instalando...

:: Eleva privilegios se necessario
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Solicitando permissao de administrador...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   PharmaIntel BR — Instalacao Automatica     ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: Vai para a pasta do script
cd /d "%~dp0"

echo  Configurando PowerShell...
powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force" >nul 2>&1
echo  OK

echo  Iniciando setup completo...
echo.

:: Roda o SETUP.ps1 sem precisar de clique direito
powershell -ExecutionPolicy Bypass -File "%~dp0SETUP.ps1"

pause
