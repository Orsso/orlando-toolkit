# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Get project root
project_root = Path(SPECPATH)

# Define paths
assets_path = project_root / 'assets'
dtd_path = project_root / 'src' / 'dtd_package'
icon_path = project_root / 'assets' / 'app_icon.ico'

a = Analysis(
    ['run.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(assets_path), 'assets'),
        (str(dtd_path), 'src/dtd_package'),
    ],
    hiddenimports=[
        'PIL._tkinter_finder',
        'sv_ttk',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'lxml.etree',
        'lxml._elementpath',
        'src.logger_config',
        'src.main',
        'src.docx_parser',
        'src.docx_to_dita_converter',
        'src.ui.metadata_tab',
        'src.ui.image_tab',
        'src.ui.custom_widgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Add sv_ttk theme files
from PyInstaller.utils.hooks import collect_all
datas, binaries, hiddenimports = collect_all('sv_ttk')
a.datas += datas
a.binaries += binaries
a.hiddenimports += hiddenimports

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OrlandoToolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
    version='version_info.txt'  # Optional: version info
) 