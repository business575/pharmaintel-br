# pharmaintel.spec
# Gera um executável standalone do PharmaIntel BR
# Uso: pyinstaller pharmaintel.spec

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    ['launcher.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        ('app.py', '.'),
        ('src', 'src'),
        ('data', 'data'),
        ('dashboard', 'dashboard'),
        ('.streamlit', '.streamlit'),
        ('requirements.txt', '.'),
    ],
    hiddenimports=[
        'streamlit',
        'streamlit.web.cli',
        'streamlit.runtime.scriptrunner',
        'plotly',
        'plotly.graph_objects',
        'plotly.express',
        'pandas',
        'numpy',
        'pyarrow',
        'tenacity',
        'requests',
        'groq',
        'dotenv',
        'loguru',
        'altair',
        'pydeck',
        'pkg_resources.py2_warn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'sklearn'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PharmaIntelBR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PharmaIntelBR',
)
