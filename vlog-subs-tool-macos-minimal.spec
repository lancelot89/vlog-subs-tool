# -*- mode: python ; coding: utf-8 -*-
"""
VLog字幕ツール macOS最小構成 PyInstaller設定ファイル
Issue #216対応: ソース実行と完全同一挙動を最優先に、不要な最適化・除外・カスタムフックを撤廃
"""

# 最小構成のblock cipher
block_cipher = None

# Analysis: 最小設定でソース実行と同一挙動を目指す
a = Analysis(
    ['app/main.py'],                     # エントリポイント一本化
    pathex=[],                           # パス設定は最小限
    binaries=[],                         # 必要なバイナリがあれば後で追加
    datas=[
        # 基本リソースのみ同梱（サイズは気にしない）
        ('README.md', '.'),
        ('app', 'app'),                  # アプリケーション全体を物理同梱
    ],
    hiddenimports=[
        # 必要最小限のみ（動作確認後に不足分を追加）
        # 最初は空で試し、ImportErrorが出た分だけ追加する方針
    ],
    hookspath=[],                        # 独自フックは使わない
    runtime_hooks=[],                    # ランタイムフックも使わない
    excludes=[],                         # 何も除外しない（デフォルトに任せる）
    noarchive=False,                     # デフォルト設定
    win_no_prefer_redirects=False,       # デフォルト設定
    win_private_assemblies=False,        # デフォルト設定
    cipher=block_cipher,
)

# PYZ: デフォルト設定
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# EXE: 最小設定（macOS用）
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,               # macOS app bundle用
    name='VLog字幕ツール',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,                         # ストリップしない
    upx=False,                          # UPX圧縮使わない
    console=False,                      # macOSではGUIアプリとして
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# COLLECT: アプリファイル収集
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,                        # ストリップしない
    upx=False,                          # UPX圧縮使わない
    upx_exclude=[],
    name='VLog字幕ツール',
)

# macOS .appバンドル作成
app = BUNDLE(
    coll,
    name='VLog字幕ツール.app',
    icon=None,
    bundle_identifier='com.vlogsubs.tool',
    version='1.0.0',
    info_plist={
        'CFBundleDisplayName': 'VLog字幕ツール',
        'CFBundleGetInfoString': 'VLOG動画字幕抽出・編集・翻訳ツール v1.0.0 - 最小構成版',
        'CFBundleIdentifier': 'com.vlogsubs.tool',
        'CFBundleInfoDictionaryVersion': '6.0',
        'CFBundleName': 'VLog字幕ツール',
        'CFBundlePackageType': 'APPL',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleSignature': 'VLOG',
        'CFBundleVersion': '1.0.0',
        'LSMinimumSystemVersion': '10.15',
        'NSHighResolutionCapable': True,
        'NSHumanReadableCopyright': '© 2024 VLog字幕ツール',
        'NSRequiresAquaSystemAppearance': False,
        'NSSupportsAutomaticGraphicsSwitching': True,

        # セキュリティ・プライバシー設定（最小限）
        'NSCameraUsageDescription': 'このアプリケーションはカメラを使用しません',
        'NSMicrophoneUsageDescription': 'このアプリケーションはマイクロフォンを使用しません',
        'NSLocationUsageDescription': 'このアプリケーションは位置情報を使用しません',

        # ネットワーク関連（デフォルト設定）
        'NSAppTransportSecurity': {
            'NSAllowsArbitraryLoads': False,
        },

        # 必要最小限の設定
        'CFBundleExecutable': 'VLog字幕ツール',
    },
)