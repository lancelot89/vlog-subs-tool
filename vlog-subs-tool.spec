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

# 隠しインポートの定義
hidden_imports = [
    # PySide6関連
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',

    # PaddleOCR関連
    'paddleocr',
    'paddlepaddle',
    'paddle',
    'paddle.fluid',
    'paddle.inference',
    'paddlex',  # PaddleXモジュール
    'paddlex.utils',
    'paddlex.utils.version',

    # OpenCV関連
    'cv2',
    'numpy',

    # その他の重要ライブラリ
    'PIL',
    'PIL.Image',
    'pytesseract',
    'google.cloud.translate',
    'google.cloud.translate_v3',
    'deepl',
    'pysrt',
    'loguru',
    'tqdm',
    'pandas',
    'yaml',
    'bidi.algorithm',

    # アプリケーション内部モジュール（完全収集）
    'app',
    'app.main',
    'app.core',
    'app.core.models',
    'app.core.extractor',
    'app.core.extractor.ocr',
    'app.core.extractor.detector',
    'app.core.format',
    'app.core.format.srt',
    'app.core.csv',
    'app.core.qc',
    'app.core.qc.rules',
    'app.core.translate',
    'app.core.translate.provider_google',
    'app.core.translate.provider_deepl',
    'app.ui',
    'app.ui.main_window',
    'app.ui.views',
    'app.ui.dialogs',
    'app.ui.dialogs.ocr_setup_dialog',
    'app.ui.dialogs.translation_dialog',
    'app.ui.dialogs.settings_dialog',
]

# データファイルの定義
datas = [
    ('README.md', '.'),
    # 組み込みPaddleOCRモデルファイル
    ('app/models', 'models'),
]

# PaddleOCR / PaddlePaddle関連のデータファイルを動的に検出・追加
try:
    import site
    import paddleocr
    import paddle
    from pathlib import Path

    # site-packages内のpaddleディレクトリを探索
    for site_dir in site.getsitepackages():
        site_path = Path(site_dir)

        # paddlexディレクトリがあれば.versionファイルをコピー
        paddlex_dir = site_path / 'paddlex'
        if paddlex_dir.exists():
            version_file = paddlex_dir / '.version'
            if version_file.exists():
                datas.append((str(version_file), 'paddlex'))
                print(f"Found PaddleX version file: {version_file}")

        # paddleディレクトリの重要ファイルをコピー
        paddle_dir = site_path / 'paddle'
        if paddle_dir.exists():
            # バージョン情報ファイル
            for version_pattern in ['version.py', '__version__.py', '.version', 'version']:
                version_file = paddle_dir / version_pattern
                if version_file.exists():
                    datas.append((str(version_file), f'paddle/{version_pattern}'))
                    print(f"Found Paddle version file: {version_file}")

            # paddlex subdirectoryがあればそれもコピー
            paddlex_subdir = paddle_dir / 'paddlex'
            if paddlex_subdir.exists():
                paddlex_version = paddlex_subdir / '.version'
                if paddlex_version.exists():
                    datas.append((str(paddlex_version), 'paddle/paddlex'))
                    print(f"Found Paddle/PaddleX version file: {paddlex_version}")

except ImportError as e:
    print(f"Warning: Could not import paddle modules: {e}")
except Exception as e:
    print(f"Warning: Error while detecting paddle data files: {e}")

# バイナリの定義（PaddleOCRモデルなど）
binaries = []

# 除外するモジュール
excludes = [
    'tkinter',
    'matplotlib',
    'IPython',
    'jupyter',
    'notebook',
    'scipy',
    'sklearn',
    'tensorflow',
    'torch',
    'torchvision',
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
    # 再帰的にすべてのモジュールを収集
    collect_all=[
        'app',
        'app.ui',
        'app.core',
        'app.core.extractor',
        'app.core.format',
        'app.core.translate',
        'app.core.qc',
    ],
    # Paddleデータファイルの明示的収集
    collect_data=[
        'paddleocr',
        'paddle',
        'paddlex',
    ],
    collect_submodules=[
        'paddleocr',
        'paddle',
        'paddlex',
    ],
)

# PYZアーカイブ作成
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

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
    console=False,  # GUIアプリケーションのためコンソールを非表示
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