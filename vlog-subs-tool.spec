# -*- mode: python ; coding: utf-8 -*-
"""
VLog字幕ツール PyInstaller設定ファイル
PaddleOCR、PySide6、OpenCVなど大型ライブラリの包含に対応
"""

import os
import sys
from pathlib import Path

# プロジェクトルートディレクトリ（CI環境対応）
if hasattr(sys, '_MEIPASS'):
    # PyInstallerで実行される場合
    project_root = Path(sys._MEIPASS)
else:
    # 通常の開発環境
    project_root = Path.cwd()

app_dir = project_root / "app"

# 隠しインポートの定義（最適化済み）
hidden_imports = [
    # PySide6関連（必須）
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',

    # PaddleOCR関連（コア機能のみ）
    'paddleocr',
    'paddlepaddle',
    'paddle',

    # OpenCV関連（必須）
    'cv2',
    'numpy',

    # 基本ライブラリ（必須）
    'PIL',
    'PIL.Image',
    'pytesseract',
    'pysrt',
    'pandas',
    'yaml',
    'bidi.algorithm',

    # CPU最適化（基本のみ）
    'psutil',

    # アプリケーション内部モジュール（必要最小限）
    'app',
    'app.main',
    'app.core',
    'app.core.models',
    'app.core.extractor',
    'app.core.extractor.ocr',
    'app.core.format',
    'app.core.format.srt',
    'app.core.csv',
    'app.core.qc',
    'app.core.qc.rules',
    'app.core.translate',
    'app.core.cpu_profiler',
    'app.ui',
    'app.ui.main_window',
    'app.ui.views',
    'app.ui.dialogs',
]

# データファイルの定義（サイズ最適化）
datas = [
    ('README.md', '.'),
]

# アプリケーションモデルファイルが存在する場合のみ追加
app_models_path = project_root / "app" / "models"
if app_models_path.exists():
    datas.append(('app/models', 'models'))
    print(f"Added app models directory: {app_models_path}")

# PaddleOCR関連のデータファイル（必要最小限）
try:
    import paddleocr
    print("PaddleOCR found - lightweight support enabled")
except ImportError as e:
    print(f"Warning: PaddleOCR not available: {e}")

# バイナリの定義（PaddleOCRモデルなど）
binaries = []

# 除外するモジュール（サイズ削減）
excludes = [
    # GUI関連（不要）
    'tkinter',
    'matplotlib',
    'wx',

    # データサイエンス・ML（不要）
    'IPython',
    'jupyter',
    'notebook',
    'scipy',
    'sklearn',
    'tensorflow',
    'torch',
    'torchvision',
    'transformers',

    # 削除された機能
    'app.core.benchmark',
    'app.core.linux_optimizer',

    # 未使用ライブラリ（サイズ削減）
    'loguru',
    'tqdm',
    'deepl',
    'google.cloud.translate',
    'google.cloud.translate_v3',
    'google.auth',
    'google.api_core',

    # 大型ライブラリ（不要）
    'openpyxl',
    'xlsxwriter',
    'xlrd',
    'seaborn',
    'plotly',

    # ネットワーク関連（OCRローカル実行のため）
    'requests_oauthlib',
    'urllib3.contrib.pyopenssl',

    # 開発ツール
    'pytest',
    'mypy',
    'black',
    'isort',
    'flake8',
]

# フックパス設定（存在する場合のみ）
hookspath_list = []
hooks_dir = project_root / "hooks"
if hooks_dir.exists():
    hookspath_list.append(str(hooks_dir))

# 分析設定（完全スタンドアロン対応）
a = Analysis(
    ['app/main.py'],
    pathex=[str(project_root), str(app_dir)],
    binaries=binaries,
    datas=datas + [
        # アプリケーション全体をバンドル
        (str(app_dir), 'app'),
    ],
    hiddenimports=hidden_imports,
    hookspath=hookspath_list,
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
    # 必要最小限のモジュール収集（サイズ最適化）
    collect_all=[
        'app',
        'app.ui',
        'app.core',
        'app.core.extractor',
        'app.core.format',
        'app.core.translate',
        'app.core.qc',
        'psutil',  # CPU情報取得
    ],
    # PaddleOCR収集（AVX/non-AVX CPU互換性確保）
    collect_data=[
        'paddleocr',
        'paddle',  # AVX/non-AVX CPU互換性のため必須
    ],
    collect_submodules=[
        'paddleocr',
        'paddle',  # paddle.fluid.core_avx/core_noavx両方をバンドル
    ],
)

# PYZアーカイブ作成
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# デバッグモード判定（環境変数または設定ファイルから判定）
# 本番ビルド時は console=False に設定
import os
DEBUG_MODE = os.environ.get('VLOG_SUBS_DEBUG', 'false').lower() == 'true'

# 実行ファイル設定（--onedir形式でウイルス誤検知を回避）
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='vlog-subs-tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX圧縮を無効化（誤検知回避）
    console=DEBUG_MODE,  # 環境変数 VLOG_SUBS_DEBUG=true でコンソール表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# ディレクトリ形式でファイルを収集
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # UPX圧縮を無効化（誤検知回避）
    upx_exclude=[],
    name='vlog-subs-tool',
)