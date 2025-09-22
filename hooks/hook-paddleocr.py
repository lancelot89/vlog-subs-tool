"""
PyInstaller hook for PaddleOCR (Issue #207 対応)
PaddleOCRのモデルとデータファイルを適切にパッケージングするためのフック
cpp_extension問題はruntime hookで解決し、paddlexは保持する
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import os

# PaddleOCRの全モジュールを収集（paddlexも含む）
try:
    datas, binaries, hiddenimports = collect_all("paddleocr")

    # PaddlePaddleのバイナリとデータも収集
    paddle_datas, paddle_binaries, paddle_hiddenimports = collect_all("paddle")
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
