"""
PyInstaller hook for OpenCV (cv2)
OpenCVのネイティブライブラリを適切にパッケージングするためのフック
"""

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs
import cv2
import os

# OpenCVの全モジュールを収集
datas, binaries, hiddenimports = collect_all('cv2')

# OpenCVの動的ライブラリを収集
opencv_binaries = collect_dynamic_libs('cv2')
binaries += opencv_binaries

# 追加の隠しインポート
hiddenimports += [
    'cv2.data',
    'numpy.core._methods',
    'numpy.lib.format',
]