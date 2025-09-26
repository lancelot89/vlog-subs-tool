# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the vlog-subs-tool application.

The goal is to mirror the behaviour of running the source tree directly.
This spec includes necessary PaddleOCR/PaddleX resources and hidden imports
while avoiding custom hooks, UPX compression or other complex optimisations.
Everything the runtime might touch is included in an onedir build.
"""

from pathlib import Path


def unique(items):
    """Return a list with duplicates removed while preserving order."""

    seen = set()
    ordered = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered

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

# Binary artifacts collected from Paddle/PaddleOCR packages.
_binaries = []

# Hidden imports for PaddleOCR and dynamically loaded modules
_hiddenimports = [
    # PySide6 GUI framework
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    # PaddleOCR core modules
    "paddleocr",
    "paddle",
    "paddle.utils",
    "paddle.fluid",
    "paddle.inference",
    # PaddleOCR inference modules (dynamically imported)
    "paddleocr.tools.infer.utility",
    "paddleocr.tools.infer.predict_system",
    "paddleocr.tools.infer.predict_det",
    "paddleocr.tools.infer.predict_rec",
    "paddleocr.tools.infer.predict_cls",
    "paddleocr.paddleocr",
    # PaddleX runtime
    "paddlex",
    # Core image processing libraries
    "cv2",
    "numpy",
    "PIL",
    "PIL.Image",
    # Other application dependencies
    "pytesseract",
    "pysrt",
    "pandas",
    "yaml",
    "bidi.algorithm",
    "psutil",
    # Application modules
    "app",
    "app.main",
    "app.core",
    "app.ui",
    "app.ui.main_window",
]

try:
    from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

    try:
        paddle_datas, paddle_binaries, paddle_hidden = collect_all("paddle")
        _datas.extend(paddle_datas)
        _binaries.extend(paddle_binaries)
        _hiddenimports.extend(paddle_hidden)
        print(
            "Collected Paddle resources: "
            f"{len(paddle_datas)} data files, {len(paddle_binaries)} binaries, "
            f"{len(paddle_hidden)} hidden imports"
        )
    except Exception as exc:  # pragma: no cover - diagnostic logging
        print(f"Warning: Failed to collect Paddle package resources: {exc}")

    try:
        paddleocr_datas, paddleocr_binaries, paddleocr_hidden = collect_all("paddleocr")
        _datas.extend(paddleocr_datas)
        _binaries.extend(paddleocr_binaries)
        _hiddenimports.extend(paddleocr_hidden)
        print(
            "Collected PaddleOCR resources: "
            f"{len(paddleocr_datas)} data files, {len(paddleocr_binaries)} binaries, "
            f"{len(paddleocr_hidden)} hidden imports"
        )
    except Exception as exc:  # pragma: no cover - diagnostic logging
        print(f"Warning: Failed to collect PaddleOCR package resources: {exc}")

    try:
        infer_submodules = collect_submodules("paddleocr.tools.infer")
        _hiddenimports.extend(infer_submodules)
        print(f"Collected {len(infer_submodules)} paddleocr.tools.infer submodules")
    except Exception as exc:  # pragma: no cover - diagnostic logging
        print(f"Warning: Failed to collect paddleocr.tools.infer submodules: {exc}")

    try:
        paddlex_datas = collect_data_files("paddlex", include_py_files=True)
        paddlex_hidden = collect_submodules("paddlex")
        _datas.extend(paddlex_datas)
        _hiddenimports.extend(paddlex_hidden)
        print(
            "Collected PaddleX resources: "
            f"{len(paddlex_datas)} data files, 0 binaries, {len(paddlex_hidden)} hidden imports"
        )
    except Exception as exc:  # pragma: no cover - diagnostic logging
        print(f"Warning: Failed to collect PaddleX package resources: {exc}")

except ImportError:  # pragma: no cover - diagnostic logging
    print("Warning: PyInstaller hooks not available, skipping Paddle resource collection")

_datas = unique(_datas)
_binaries = unique(_binaries)
_hiddenimports = unique(_hiddenimports)

a = Analysis(
    ["app/main.py"],
    pathex=[str(project_root)],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hiddenimports,
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
