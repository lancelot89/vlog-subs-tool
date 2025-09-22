# hooks/rthook-paddlex-reinit-guard.py
"""
PyInstaller ランタイムフック - PaddleX完全初期化ブロック

Issue #214 対応: PaddleXが複数回初期化されるエラー
"PDX has already been initialized. Reinitialization is not supported."
を防ぐため、PaddleX初期化を完全にブロックし、ダミー実装で置き換える。
"""

import sys
import types
import logging

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_minimal_paddlex_stub():
    """PaddleXの最小限のスタブを作成してPaddleOCRインポートを可能にする"""
    try:
        # PaddleXがインポート済みの場合は削除
        paddlex_modules = [mod for mod in sys.modules.keys() if mod.startswith('paddlex')]
        for mod in paddlex_modules:
            del sys.modules[mod]
            logger.info(f"Removed existing PaddleX module: {mod}")

        # 最小限のPaddleXスタブモジュールを作成
        paddlex = types.ModuleType('paddlex')
        paddlex._initialized = True  # 初期化済みフラグ
        paddlex.__version__ = "3.2.1"
        paddlex.__path__ = []

        # スタブ初期化関数
        def stub_initialize(*args, **kwargs):
            """PaddleX初期化のスタブ - 何もしない"""
            logger.debug("PaddleX initialization bypassed (stub)")
            return

        paddlex.initialize = stub_initialize

        # paddlex.inference.utils.benchmark スタブ
        inference_utils = types.ModuleType('paddlex.inference.utils')
        inference_utils.__path__ = []

        benchmark_module = types.ModuleType('paddlex.inference.utils.benchmark')

        def stub_benchmark(*args, **kwargs):
            """benchmark関数のスタブ - ダミー値を返す"""
            logger.debug("PaddleX benchmark called (stub)")
            return {"inference_time": 0.0, "preprocess_time": 0.0, "postprocess_time": 0.0}

        benchmark_module.benchmark = stub_benchmark

        # paddlex.inference スタブ
        inference = types.ModuleType('paddlex.inference')
        inference.__path__ = []
        inference.utils = inference_utils

        # paddlex.repo_manager.core スタブ
        repo_manager = types.ModuleType('paddlex.repo_manager')
        repo_manager.__path__ = []

        core = types.ModuleType('paddlex.repo_manager.core')
        core.initialize = stub_initialize

        repo_manager.core = core

        # PaddleXモジュール階層構築
        paddlex.inference = inference
        paddlex.repo_manager = repo_manager

        # sys.modules に登録
        sys.modules['paddlex'] = paddlex
        sys.modules['paddlex.inference'] = inference
        sys.modules['paddlex.inference.utils'] = inference_utils
        sys.modules['paddlex.inference.utils.benchmark'] = benchmark_module
        sys.modules['paddlex.repo_manager'] = repo_manager
        sys.modules['paddlex.repo_manager.core'] = core

        logger.info("PaddleX stub modules created successfully")

    except Exception as e:
        logger.error(f"Failed to create PaddleX stub: {e}")


def block_paddlex_initialization():
    """PaddleX初期化を完全にブロック"""
    # 最初にスタブを作成
    create_minimal_paddlex_stub()

    # インポートフックでPaddleXをスタブで置き換え
    original_import = __builtins__.__import__

    def hooked_import(name, *args, **kwargs):
        if name == 'paddlex' or name.startswith('paddlex.'):
            # 既にスタブが作成されている場合はそれを返す
            if name in sys.modules:
                logger.debug(f"Returning PaddleX stub for: {name}")
                return sys.modules[name]

        return original_import(name, *args, **kwargs)

    __builtins__.__import__ = hooked_import
    logger.info("PaddleX import hook installed")


# PyInstaller実行時のみPaddleX初期化をブロック
if hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False):
    logger.info("Binary execution detected - blocking PaddleX initialization")
    block_paddlex_initialization()