# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

added_files = [
    ("desktop/app.py", "desktop"),
    ("shared/translation_core.py", "shared"),
    ("shared/__init__.py", "shared"),
    ("desktop/.env.example", "."),
]

hidden = collect_submodules("PIL") + [
    "requests",
    "urllib3",
    "certifi",
    "charset_normalizer",
    "idna",
    "tkinter",
    "_tkinter",
]

# 打包 tkinter / Tcl / Tk 运行时
_tk_datas, _tk_binaries, _tk_hidden = collect_all("tkinter")
added_files += _tk_datas
binaries = _tk_binaries
hidden += _tk_hidden

a = Analysis(
    ["translate_helper/launcher.py"],
    pathex=["."],
    binaries=binaries,
    datas=added_files,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TranslateHelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TranslateHelper",
)
