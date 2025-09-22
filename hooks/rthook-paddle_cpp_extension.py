# -*- coding: utf-8 -*-
"""
PyInstaller Runtime Hook for Paddle C++ Extension Prevention
Issue #207 対応: paddlepaddle 3.0.0 の cpp_extension.load() クラッシュを防ぐ

PaddlePaddleの cpp_extension.load() 関数が PyInstaller 実行時に
C++ コンパイルを試行してクラッシュする問題を解決するため、
この関数をスタブ化して無害な関数に置き換える。
"""

import sys
import logging
from unittest.mock import Mock

# スタブ関数の定義
def stub_cpp_extension_load(*args, **kwargs):
    """
    cpp_extension.load() のスタブ実装
    PyInstaller環境では C++ コンパイルを実行せず、
    無害なMockオブジェクトを返す
    """
    logging.warning("cpp_extension.load() called in PyInstaller environment - returning stub")
    return Mock()

def stub_cpp_extension_setup(*args, **kwargs):
    """
    cpp_extension.setup() のスタブ実装
    """
    logging.warning("cpp_extension.setup() called in PyInstaller environment - returning stub")
    return Mock()

# PyInstaller環境での paddlepaddle.utils.cpp_extension のパッチ
if hasattr(sys, '_MEIPASS'):
    try:
        # paddlepaddle がインポート済みの場合のパッチ
        if 'paddle' in sys.modules:
            import paddle
            if hasattr(paddle, 'utils') and hasattr(paddle.utils, 'cpp_extension'):
                paddle.utils.cpp_extension.load = stub_cpp_extension_load
                paddle.utils.cpp_extension.setup = stub_cpp_extension_setup
                logging.info("Patched paddle.utils.cpp_extension functions")

        # 将来的なインポートに備えた import hook
        def patch_cpp_extension():
            try:
                import paddle.utils.cpp_extension
                paddle.utils.cpp_extension.load = stub_cpp_extension_load
                paddle.utils.cpp_extension.setup = stub_cpp_extension_setup
                logging.info("Patched paddle.utils.cpp_extension via import hook")
            except ImportError:
                # paddle または cpp_extension が利用できない場合は無視
                pass

        # 遅延パッチのためのフック登録
        original_import = __builtins__.__import__

        def patched_import(name, *args, **kwargs):
            module = original_import(name, *args, **kwargs)
            if name.startswith('paddle') and 'cpp_extension' in name:
                patch_cpp_extension()
            return module

        __builtins__.__import__ = patched_import

        logging.info("paddle cpp_extension runtime hook loaded successfully")

    except Exception as e:
        logging.warning(f"Failed to apply paddle cpp_extension patch: {e}")