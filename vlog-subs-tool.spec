# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the vlog-subs-tool application.

The goal is to mirror the behaviour of running the source tree directly.
This spec includes necessary PaddleOCR resources and hidden imports while
avoiding custom hooks, module exclusions, UPX compression or other complex
optimisations. Everything the runtime might touch is included in an onedir
build.  A local hook directory is registered so we can bundle paddlex' data
files (notably the `.version` marker) that PaddleOCR accesses lazily.
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

# Collect PaddleOCR data files (YAML/dictionary/config files) for OCR functionality
try:
    from PyInstaller.utils.hooks import collect_data_files

    # Collect PaddleOCR's configuration and dictionary files
    paddleocr_datas = collect_data_files(
        "paddleocr", includes=["**/*.yml", "**/*.yaml", "**/*.json", "**/*.txt", "**/*.dict"]
    )
    _datas.extend(paddleocr_datas)
    print(f"Collected {len(paddleocr_datas)} PaddleOCR data files")

    # Collect Paddle core configuration files
    paddle_datas = collect_data_files("paddle", includes=["**/*.yml", "**/*.yaml", "**/*.json"])
    _datas.extend(paddle_datas)
    print(f"Collected {len(paddle_datas)} Paddle data files")

    try:
        paddlex_datas = collect_data_files(
            "paddlex",
            includes=[
                ".version",
                "*.version",
                "**/.version",
                "**/*.yml",
                "**/*.yaml",
                "**/*.json",
                "**/*.txt",
            ],
        )
        _datas.extend(paddlex_datas)
        if paddlex_datas:
            print(f"Collected {len(paddlex_datas)} PaddleX data files")
    except ModuleNotFoundError:
        print("PaddleX is not installed; skipping PaddleX data collection")

except ImportError:
    print("Warning: PyInstaller hooks not available, skipping data collection")
except Exception as e:
    print(f"Warning: Data collection failed: {e}")

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
    "paddlepaddle",
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

a = Analysis(
    ["app/main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[str(project_root / "hooks")],
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
