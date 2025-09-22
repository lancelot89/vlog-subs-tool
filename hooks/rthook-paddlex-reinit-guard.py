# hooks/rthook-paddlex-reinit-guard.py
"""
PyInstaller ランタイムフック - PaddleX重複初期化防止

Issue #214 対応: PaddleXが複数回初期化されるエラー
"PDX has already been initialized. Reinitialization is not supported."
を防ぐため、PaddleX初期化を制御する。実際のPaddleXを使用しつつ重複初期化のみを防止。
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


def prevent_paddlex_reinitialization():
    """PaddleX重複初期化を防止（実際のPaddleXを使用）"""
    global _paddlex_initialized

    try:
        import paddlex
        import paddlex.repo_manager.core

        logger.info("Applying PaddleX reinitialization guard (using real PaddleX)")

        with _init_lock:
            if _paddlex_initialized:
                logger.info("PaddleX guard already applied")
                return

            # 元の初期化関数を保存
            original_initialize = paddlex.repo_manager.core.initialize

            def guarded_initialize(*args, **kwargs):
                """重複初期化を防ぐガード付き初期化関数"""
                global _paddlex_initialized

                with _init_lock:
                    if _paddlex_initialized:
                        logger.info("PaddleX reinitialization attempt blocked")
                        return

                    logger.info("Performing PaddleX initialization (first time)")
                    try:
                        result = original_initialize(*args, **kwargs)
                        _paddlex_initialized = True
                        logger.info("PaddleX initialization completed successfully")
                        return result
                    except Exception as e:
                        if "already been initialized" in str(e):
                            logger.info("PaddleX was already initialized elsewhere")
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

            _paddlex_initialized = True
            logger.info("PaddleX reinitialization guard applied successfully")

    except ImportError:
        logger.info("PaddleX not available - reinitialization guard not needed")
    except Exception as e:
        logger.error(f"Failed to apply PaddleX reinitialization guard: {e}")


# PyInstaller実行時のみPaddleX重複初期化を防止
if hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False):
    logger.info("Binary execution detected - preventing PaddleX reinitialization")

    # できるだけ早い段階でPaddleX環境変数を設定
    import os
    os.environ.setdefault("PADDLEX_DISABLE_AUTO_INIT", "1")

    # 遅延初期化でPaddleXガードを適用
    def delayed_paddlex_guard():
        try:
            prevent_paddlex_reinitialization()
        except Exception as e:
            logger.error(f"Delayed PaddleX guard failed: {e}")

    # PaddleX関連モジュールがインポートされる前にガードを設定
    original_import = __builtins__.__import__

    def hooked_import(name, *args, **kwargs):
        if name.startswith('paddlex') and not getattr(hooked_import, '_guard_applied', False):
            logger.info("PaddleX import detected - applying guard")
            delayed_paddlex_guard()
            hooked_import._guard_applied = True

        return original_import(name, *args, **kwargs)

    __builtins__.__import__ = hooked_import
    logger.info("PaddleX import hook installed")