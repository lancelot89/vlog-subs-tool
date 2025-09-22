"""
PyInstaller hook for PaddleOCR (Issue #214 対応)
PaddleOCRのモデルとデータファイルを適切にパッケージングするためのフック
PaddleXを正式依存関係として含む
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import os

# PaddleOCRの全モジュールを収集（Issue #214: PaddleX含む）
try:
    datas, binaries, hiddenimports = collect_all("paddleocr")

    # PaddlePaddleのバイナリとデータも収集（Issue #214: PaddleX含む）
    paddle_datas, paddle_binaries, paddle_hiddenimports = collect_all("paddle")

    # PaddleXも正式に収集（Issue #214対応）
    try:
        paddlex_datas, paddlex_binaries, paddlex_hiddenimports = collect_all("paddlex")
        datas += paddlex_datas
        binaries += paddlex_binaries
        hiddenimports += paddlex_hiddenimports
    except ImportError:
        print("Warning: PaddleX collection failed - continuing without PaddleX data")

    # PaddleX大型モジュールのみ除外（OCRに不要な機能）
    exclude_paddlex = ['paddlex.deploy', 'paddlex.pipelines.auto_compress', 'paddlex.models.llm', 'paddlex.models.speech']
    paddle_hiddenimports = [imp for imp in paddle_hiddenimports if not any(imp.startswith(exc) for exc in exclude_paddlex)]

    datas += paddle_datas
    binaries += paddle_binaries
    hiddenimports += paddle_hiddenimports

except ImportError as e:
    # インポートエラーの場合は警告を出すが継続
    print(f"Warning: PaddleOCR collection failed, trying minimal approach: {e}")
    datas = []
    binaries = []
    hiddenimports = []

# 追加の隠しインポート（Issue #214対応: PaddleX含む）
hiddenimports += [
    "paddle.fluid",
    "paddle.inference",
    "paddle.utils",
    "paddle.utils.cpp_extension",  # runtime hookで安全化
    "paddleocr.tools.infer.utility",
    "paddleocr.tools.infer.predict_system",
    "paddleocr.paddleocr",
    # PaddleX関連
    "paddlex",
    "paddlex.inference",
    "paddlex.inference.utils",
    "paddlex.inference.utils.benchmark",
    "paddlex.utils",
    "paddlex.utils.device",
    "paddlex.utils.deps",
    "paddlex.repo_manager",
    "paddlex.repo_manager.core",
]

# モデルファイル用のデータ収集
try:
    model_datas = collect_data_files(
        "paddleocr", includes=["**/*.yml", "**/*.yaml", "**/*.json"]
    )
    datas += model_datas
except Exception:
    pass
