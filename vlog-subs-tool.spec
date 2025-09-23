# -*- mode: python ; coding: utf-8 -*-
"""Minimal PyInstaller spec for the vlog-subs-tool application.

The goal is to mirror the behaviour of running the source tree directly, so
this spec intentionally avoids custom hooks, module exclusions, UPX
compression or other optimisations.  Everything the runtime might touch is
included as-is in an onedir build.
"""

from pathlib import Path

block_cipher = None

try:
    project_root = Path(__file__).resolve().parent
except NameError:
    project_root = Path.cwd()

# Bundle configuration files and locally cached OCR models alongside the
# executable so runtime lookups behave the same as in a source checkout.
_datas = [
    (str(project_root / "app" / "config"), "app/config"),
    (str(project_root / "app" / "models"), "app/models"),
]

a = Analysis(
    ["app/main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=_datas,
    hiddenimports=[],
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
    name="vlog-subs-tool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    upx=False,
    upx_exclude=[],
    name="vlog-subs-tool",
)
