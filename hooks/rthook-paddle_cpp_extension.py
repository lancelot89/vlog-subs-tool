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
    # PaddleX初期化問題を回避するため、環境変数を事前に設定
    import os
    os.environ.setdefault("PADDLEX_DISABLE_AUTO_INIT", "1")

    try:
        # 遅延パッチング: cpp_extensionインポート時のみ処理
        def patch_cpp_extension_on_import():
            try:
                import paddle.utils.cpp_extension
                paddle.utils.cpp_extension.load = stub_cpp_extension_load
                paddle.utils.cpp_extension.setup = stub_cpp_extension_setup
                logging.info("Patched paddle.utils.cpp_extension functions")
            except ImportError:
                pass

        # 最小限のimport hookでcpp_extensionのみを対象
        original_import = __builtins__.__import__

        def safe_import_hook(name, *args, **kwargs):
            module = original_import(name, *args, **kwargs)
            # cpp_extensionモジュールのみパッチ
            if name == 'paddle.utils.cpp_extension':
                try:
                    module.load = stub_cpp_extension_load
                    module.setup = stub_cpp_extension_setup
                    logging.info(f"Patched {name} successfully")
                except AttributeError:
                    pass
            return module

        __builtins__.__import__ = safe_import_hook
        logging.info("Minimal cpp_extension hook installed")

    except Exception as e:
        logging.warning(f"Failed to install cpp_extension hook: {e}")