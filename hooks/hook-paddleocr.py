"""
PyInstaller hook for PaddleOCR (Issue #207 対応)
PaddleOCRのモデルとデータファイルを適切にパッケージングするためのフック
paddlex依存関係問題を回避し、安全にPaddleOCRをビルドする
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import os

# Issue #207対応: paddlexインポートエラーを防ぐため、
# 安全にPaddleOCRを収集する
datas = []
binaries = []
hiddenimports = []

# PaddleOCRの基本モジュールを安全に収集
try:
    # paddlexに依存しない基本的な収集のみ実行
    paddle_datas, paddle_binaries, paddle_hiddenimports = collect_all("paddle", filter_submodules=lambda name: not name.startswith('paddlex'))
    datas += paddle_datas
    binaries += paddle_binaries
    hiddenimports += paddle_hiddenimports

    # PaddleOCR基本モジュール（paddlex依存を除外）
    ocr_submodules = collect_submodules("paddleocr", filter=lambda name: not name.startswith('paddleocr.paddlex'))
    hiddenimports += ocr_submodules

    # モデルファイル用のデータ収集
    model_datas = collect_data_files("paddleocr", includes=["**/*.yml", "**/*.yaml", "**/*.json"])
    datas += model_datas

except ImportError as e:
    # paddlexエラーの場合は警告を出すが継続
    if 'paddlex' in str(e):
        print(f"Warning: PaddleX dependency issue detected, excluding from build: {e}")
    else:
        print(f"Warning: PaddleOCR collection failed: {e}")
except Exception as e:
    print(f"Warning: PaddleOCR hook failed: {e}")

# 必要最小限の隠しインポート（Issue #207対応で安全なもののみ）
hiddenimports += [
    "paddle.fluid",
    "paddle.inference",
    "paddle.utils",
    "paddle.utils.cpp_extension",  # cpp_extension問題対応
]

# paddlexを明示的に除外
excludedimports = [
    "paddlex",
    "paddlex.inference",
    "paddlex.deploy",
]
