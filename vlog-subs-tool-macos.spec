# -*- mode: python ; coding: utf-8 -*-
"""
VLog字幕ツール macOS専用 PyInstaller設定ファイル
.appバンドル形式でPaddleOCR、PySide6、OpenCVなど大型ライブラリを包含
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
]

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
)

# PYZアーカイブ作成
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 実行ファイル設定
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VLog字幕ツール',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX圧縮を無効化（誤検知回避）
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# macOS .appバンドル作成
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # UPX圧縮を無効化（誤検知回避）
    upx_exclude=[],
    name='VLog字幕ツール',
)

# .appバンドル設定
app = BUNDLE(
    coll,
    name='VLog字幕ツール.app',
    icon=None,
    bundle_identifier='com.vlogsubs.tool',
    version='1.0.5',
    info_plist={
        'CFBundleDisplayName': 'VLog字幕ツール',
        'CFBundleGetInfoString': 'VLOG動画字幕抽出・編集・翻訳ツール v1.0.5 - 完全スタンドアロン対応',
        'CFBundleIdentifier': 'com.vlogsubs.tool',
        'CFBundleInfoDictionaryVersion': '6.0',
        'CFBundleName': 'VLog字幕ツール',
        'CFBundlePackageType': 'APPL',
        'CFBundleShortVersionString': '1.0.5',
        'CFBundleSignature': 'VLOG',
        'CFBundleVersion': '1.0.5',
        'LSMinimumSystemVersion': '10.15',
        'NSHighResolutionCapable': True,
        'NSHumanReadableCopyright': '© 2024 VLog字幕ツール',
        'NSRequiresAquaSystemAppearance': False,
        'NSSupportsAutomaticGraphicsSwitching': True,

        # セキュリティ・プライバシー設定
        'NSCameraUsageDescription': 'このアプリケーションはカメラを使用しません',
        'NSMicrophoneUsageDescription': 'このアプリケーションはマイクロフォンを使用しません',
        'NSLocationUsageDescription': 'このアプリケーションは位置情報を使用しません',

        # ネットワーク関連
        'NSAppTransportSecurity': {
            'NSAllowsArbitraryLoads': False,
            'NSExceptionDomains': {}
        },

        # Gatekeeper対応
        'CFBundleExecutable': 'VLog字幕ツール',
        'CFBundleInfoDictionaryVersion': '6.0',
    },
)