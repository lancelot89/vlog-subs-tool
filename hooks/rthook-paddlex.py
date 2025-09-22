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

    # benchmark 関数のダミー実装
    def benchmark(*args, **kwargs):
        """ダミーのbenchmark関数 - 何もせずNoneを返す"""
        return None

    # create_predictor 関数のダミー実装
    def create_predictor(*args, **kwargs):
        """ダミーのcreate_predictor関数 - Mockオブジェクトを返す"""
        from unittest.mock import Mock
        return Mock()

    # ダミー初期化関数
    def initialize(*args, **kwargs):
        """ダミーの初期化関数 - 何もしない"""
        pass

    # paddlex メインモジュール
    paddlex = types.ModuleType('paddlex')
    paddlex._is_stub = True  # スタブであることを示すフラグ
    paddlex.__path__ = []  # パッケージとしてマーク
    paddlex.initialize = initialize
    paddlex._initialized = False  # 初期化フラグ
    paddlex.create_predictor = create_predictor  # PaddleOCRが必要とする関数

    # paddlex.inference サブモジュール
    inference = types.ModuleType('paddlex.inference')
    inference._is_stub = True
    inference.__path__ = []  # パッケージとしてマーク
    inference.create_predictor = create_predictor

    # PaddlePredictorOption クラス
    class PaddlePredictorOption:
        def __init__(self, *args, **kwargs):
            pass
    inference.PaddlePredictorOption = PaddlePredictorOption

    # paddlex.inference.utils サブモジュール
    utils = types.ModuleType('paddlex.inference.utils')
    utils._is_stub = True
    utils.__path__ = []  # パッケージとしてマーク
    utils.benchmark = benchmark

    # paddlex.inference.utils.benchmark サブモジュール
    benchmark_module = types.ModuleType('paddlex.inference.utils.benchmark')
    benchmark_module._is_stub = True
    benchmark_module.benchmark = benchmark

    # paddlex.utils サブモジュール（PaddleOCRが必要とする）
    paddlex_utils = types.ModuleType('paddlex.utils')
    paddlex_utils._is_stub = True
    paddlex_utils.__path__ = []

    # PaddleOCRが必要とするpaddlex.utilsのサブモジュール
    # DependencyError クラス
    class DependencyError(Exception):
        pass

    # deps サブモジュール
    deps = types.ModuleType('paddlex.utils.deps')
    deps._is_stub = True
    deps.DependencyError = DependencyError

    # config サブモジュール
    config = types.ModuleType('paddlex.utils.config')
    config._is_stub = True
    # AttrDict クラス
    class AttrDict(dict):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError:
                return None
        def __setattr__(self, key, value):
            self[key] = value
    config.AttrDict = AttrDict

    # pipeline_arguments サブモジュール
    pipeline_arguments = types.ModuleType('paddlex.utils.pipeline_arguments')
    pipeline_arguments._is_stub = True
    # custom_type 関数
    def custom_type(*args, **kwargs):
        return lambda x: x  # ダミーの型変換関数
    pipeline_arguments.custom_type = custom_type

    # paddlex.utils にサブモジュールを追加
    paddlex_utils.deps = deps
    paddlex_utils.config = config
    paddlex_utils.pipeline_arguments = pipeline_arguments

    # モジュール構造を構築
    inference.utils = utils
    paddlex.inference = inference
    paddlex.utils = paddlex_utils

    # sys.modules に登録（ネストしたインポートに対応）
    sys.modules['paddlex'] = paddlex
    sys.modules['paddlex.inference'] = inference
    sys.modules['paddlex.inference.utils'] = utils
    sys.modules['paddlex.inference.utils.benchmark'] = benchmark_module
    sys.modules['paddlex.utils'] = paddlex_utils
    sys.modules['paddlex.utils.deps'] = deps
    sys.modules['paddlex.utils.config'] = config
    sys.modules['paddlex.utils.pipeline_arguments'] = pipeline_arguments


# PyInstaller 実行時のみスタブを作成
if hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False):
    create_paddlex_stub()