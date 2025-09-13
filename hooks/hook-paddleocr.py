"""
PyInstaller hook for PaddleOCR
PaddleOCRのモデルとデータファイルを適切にパッケージングするためのフック
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import os

# PaddleOCRの全モジュールを収集
datas, binaries, hiddenimports = collect_all('paddleocr')

# PaddlePaddleのバイナリとデータも収集
paddle_datas, paddle_binaries, paddle_hiddenimports = collect_all('paddle')
datas += paddle_datas
binaries += paddle_binaries
hiddenimports += paddle_hiddenimports

# 追加の隠しインポート
hiddenimports += [
    'paddle.fluid',
    'paddle.inference',
    'paddleocr.tools.infer.utility',
    'paddleocr.tools.infer.predict_system',
    'paddleocr.paddleocr',
]

# モデルファイル用のデータ収集
try:
    model_datas = collect_data_files('paddleocr', includes=['**/*.yml', '**/*.yaml', '**/*.json'])
    datas += model_datas
except Exception:
    pass