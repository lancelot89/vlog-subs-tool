# hooks/rthook-paddlex.py
"""
PyInstaller ランタイムフック - paddlex モジュールの完全スタブ化

Issue #204 対応: PaddleOCRが暗黙的に paddlex をimportしようとする問題を解決
paddlex を使用していないにも関わらず、PaddleOCRの __init__.py で
"from paddlex.inference.utils.benchmark import benchmark" が実行され、
バイナリ起動時に "PDX has already been initialized" エラーが発生する問題を防ぐ。

このフックにより、paddlex が import されてもダミーモジュールで置き換えられ、
初期化エラーを回避する。
"""

import sys
import types


def create_paddlex_stub():
    """paddlex モジュールのスタブを作成"""
    # 既に本物のpaddlexがロードされている場合は何もしない
    if 'paddlex' in sys.modules and not getattr(sys.modules['paddlex'], '_is_stub', False):
        return

    # paddlex メインモジュール
    paddlex = types.ModuleType('paddlex')
    paddlex._is_stub = True  # スタブであることを示すフラグ

    # paddlex.inference サブモジュール
    inference = types.ModuleType('paddlex.inference')
    inference._is_stub = True

    # paddlex.inference.utils サブモジュール
    utils = types.ModuleType('paddlex.inference.utils')
    utils._is_stub = True

    # benchmark 関数のダミー実装
    def benchmark(*args, **kwargs):
        """ダミーのbenchmark関数 - 何もせずNoneを返す"""
        return None

    # ダミー初期化関数
    def initialize(*args, **kwargs):
        """ダミーの初期化関数 - 何もしない"""
        pass

    # モジュール構造を構築
    utils.benchmark = benchmark
    inference.utils = utils
    paddlex.inference = inference
    paddlex.initialize = initialize
    paddlex._initialized = False  # 初期化フラグ

    # sys.modules に登録
    sys.modules['paddlex'] = paddlex
    sys.modules['paddlex.inference'] = inference
    sys.modules['paddlex.inference.utils'] = utils


# PyInstaller 実行時のみスタブを作成
if hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False):
    create_paddlex_stub()