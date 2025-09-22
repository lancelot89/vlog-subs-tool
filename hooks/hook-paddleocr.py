"""
PyInstaller hook for PaddleOCR (Issue #207 対応)
PaddleOCRのモデルとデータファイルを適切にパッケージングするためのフック
PaddleXは完全に除外し、PaddleOCRのみ使用
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import os

# PaddleOCRの全モジュールを収集（PaddleXは除外）
try:
    datas, binaries, hiddenimports = collect_all("paddleocr")

    # PaddlePaddleのバイナリとデータも収集（PaddleX関連は除外）
    paddle_datas, paddle_binaries, paddle_hiddenimports = collect_all("paddle")

    # PaddleX関連を除外
    paddle_hiddenimports = [imp for imp in paddle_hiddenimports if not imp.startswith("paddlex")]

    datas += paddle_datas
    binaries += paddle_binaries
    hiddenimports += paddle_hiddenimports

except ImportError as e:
    # インポートエラーの場合は警告を出すが継続
    print(f"Warning: PaddleOCR collection failed, trying minimal approach: {e}")
    datas = []
    binaries = []
    hiddenimports = []

# 追加の隠しインポート（Issue #207対応）
hiddenimports += [
    "paddle.fluid",
    "paddle.inference",
    "paddle.utils",
    "paddle.utils.cpp_extension",  # runtime hookで安全化
    "paddleocr.tools.infer.utility",
    "paddleocr.tools.infer.predict_system",
    "paddleocr.paddleocr",
]

# モデルファイル用のデータ収集
try:
    model_datas = collect_data_files(
        "paddleocr", includes=["**/*.yml", "**/*.yaml", "**/*.json"]
    )
    datas += model_datas
except Exception:
    pass
