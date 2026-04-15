"""
launcher.py
===========
Ponto de entrada para o executável standalone (PyInstaller).
Inicia o Streamlit e abre o browser automaticamente.
"""
import sys
import os
import threading
import webbrowser
import time
from pathlib import Path

def open_browser():
    time.sleep(3)
    webbrowser.open("http://localhost:8501")

def main():
    # Garante que a pasta do exe é o diretório de trabalho
    if getattr(sys, 'frozen', False):
        os.chdir(Path(sys.executable).parent)

    print("=" * 50)
    print("  PharmaIntel BR — Iniciando dashboard...")
    print("  URL: http://localhost:8501")
    print("  Para encerrar: feche esta janela")
    print("=" * 50)

    # Abre browser em background
    threading.Thread(target=open_browser, daemon=True).start()

    # Inicia Streamlit
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", "app.py",
        "--server.headless", "false",
        "--server.port", "8501",
        "--browser.gatherUsageStats", "false",
    ]
    sys.exit(stcli.main())

if __name__ == "__main__":
    main()
