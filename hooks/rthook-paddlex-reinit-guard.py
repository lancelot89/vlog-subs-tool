# hooks/rthook-paddlex-reinit-guard.py
"""
PyInstaller ランタイムフック - PaddleX重複初期化防止

Issue #214 対応: PaddleXが複数回初期化されるエラー
"PDX has already been initialized. Reinitialization is not supported."
を防ぐため、PaddleX初期化を最初の1回のみに制限する。
"""

import sys
import logging
import threading

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 初期化状態管理
_paddlex_initialized = False
_init_lock = threading.Lock()


def patch_paddlex_initialization():
    """PaddleX初期化を制御してReinitialization errorを防ぐ"""
    global _paddlex_initialized

    try:
        import paddlex
        import paddlex.repo_manager.core

        logger.info("Applying PaddleX reinitialization guard")

        # 元の初期化関数を保存
        original_initialize = paddlex.repo_manager.core.initialize

        def guarded_initialize(*args, **kwargs):
            """重複初期化を防ぐガード付き初期化関数"""
            global _paddlex_initialized

            with _init_lock:
                if _paddlex_initialized:
                    logger.info("PaddleX reinitialization attempt blocked - already initialized")
                    return

                logger.info("Performing PaddleX initialization (first time)")
                try:
                    result = original_initialize(*args, **kwargs)
                    _paddlex_initialized = True
                    logger.info("PaddleX initialization completed successfully")
                    return result
                except Exception as e:
                    if "already been initialized" in str(e):
                        logger.info("PaddleX was already initialized elsewhere - marking as completed")
                        _paddlex_initialized = True
                        return
                    else:
                        logger.error(f"PaddleX initialization failed: {e}")
                        raise

        # 初期化関数を置き換え
        paddlex.repo_manager.core.initialize = guarded_initialize

        # paddlex.initialize も存在する場合は同様にパッチ
        if hasattr(paddlex, 'initialize'):
            original_paddlex_init = paddlex.initialize

            def guarded_paddlex_init(*args, **kwargs):
                global _paddlex_initialized

                with _init_lock:
                    if _paddlex_initialized:
                        logger.info("PaddleX.initialize reinitialization attempt blocked")
                        return

                    try:
                        result = original_paddlex_init(*args, **kwargs)
                        _paddlex_initialized = True
                        return result
                    except Exception as e:
                        if "already been initialized" in str(e):
                            _paddlex_initialized = True
                            return
                        raise

            paddlex.initialize = guarded_paddlex_init

        logger.info("PaddleX reinitialization guard applied successfully")

    except ImportError:
        logger.debug("PaddleX not available - skipping reinitialization guard")
    except Exception as e:
        logger.error(f"Failed to apply PaddleX reinitialization guard: {e}")


# PyInstaller実行時のみガードを適用
if hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False):
    patch_paddlex_initialization()