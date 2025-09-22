"""
PaddleX初期化ガード - バイナリ実行時の重複初期化を防止

Issue #200 対応: PaddleXの「PDX has already been initialized」エラーを解決
"""

import functools
import logging
import os
import sys
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# グローバル状態管理
_paddlex_initialized = False
_paddlex_init_lock = threading.Lock()
_paddlex_module: Optional[Any] = None


def is_paddlex_available() -> bool:
    """PaddleXが利用可能かどうかを確認"""
    try:
        import importlib.util

        return importlib.util.find_spec("paddlex") is not None
    except ImportError:
        return False


def get_paddlex_init_status() -> dict:
    """PaddleX初期化状態を取得（デバッグ用）"""
    return {
        "paddlex_available": is_paddlex_available(),
        "paddlex_initialized": _paddlex_initialized,
        "is_frozen": getattr(sys, "frozen", False),
        "is_binary": hasattr(sys, "_MEIPASS"),
    }


def ensure_paddlex_single_init() -> None:
    """PaddleXの単一初期化を保証"""
    global _paddlex_initialized, _paddlex_module

    if not is_paddlex_available():
        logger.debug("PaddleX not available, skipping initialization guard")
        return

    with _paddlex_init_lock:
        if _paddlex_initialized:
            logger.debug("PaddleX already initialized, skipping")
            return

        try:
            # 環境変数でPaddleXの動作を制御
            os.environ.setdefault("PADDLEX_DISABLE_AUTO_INIT", "1")
            os.environ.setdefault("PADDLEX_INIT_MODE", "manual")

            # バイナリ実行時の特別な設定
            if getattr(sys, "frozen", False):
                logger.info("Binary execution detected, applying PaddleX binary-safe settings")
                os.environ.setdefault("PADDLEX_BINARY_MODE", "1")
                os.environ.setdefault("PADDLEX_CACHE_DISABLED", "1")

            # PaddleXを遅延インポート
            import paddlex

            _paddlex_module = paddlex

            # 初期化フラグをチェック
            if hasattr(paddlex, "_initialized") and paddlex._initialized:
                logger.warning("PaddleX was already initialized by another module")
                _paddlex_initialized = True
                return

            # 手動初期化（必要な場合のみ）
            if hasattr(paddlex, "initialize") and not _paddlex_initialized:
                logger.info("Initializing PaddleX manually")
                paddlex.initialize()

            _paddlex_initialized = True
            logger.info("PaddleX initialization guard successful")

        except Exception as e:
            logger.error(f"PaddleX initialization guard failed: {e}")
            # 初期化に失敗した場合でもフラグを立てて再試行を防ぐ
            _paddlex_initialized = True
            raise


def safe_paddlex_import() -> Optional[Any]:
    """安全なPaddleXインポート（重複初期化防止付き）"""
    if not is_paddlex_available():
        return None

    ensure_paddlex_single_init()
    return _paddlex_module


def reset_paddlex_state() -> None:
    """PaddleX状態をリセット（テスト用）"""
    global _paddlex_initialized, _paddlex_module
    with _paddlex_init_lock:
        _paddlex_initialized = False
        _paddlex_module = None
        logger.debug("PaddleX state reset")


def prevent_paddlex_autoinit(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    デコレータ: PaddleXの自動初期化を防止
    PaddleOCR使用前に適用することで重複初期化を防ぐ
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # 環境変数で自動初期化を無効化
        old_env = os.environ.get("PADDLEX_DISABLE_AUTO_INIT")
        os.environ["PADDLEX_DISABLE_AUTO_INIT"] = "1"

        try:
            # 事前にPaddleX初期化ガードを実行
            if is_paddlex_available():
                ensure_paddlex_single_init()

            result = func(*args, **kwargs)
            return result
        finally:
            # 環境変数を元に戻す
            if old_env is None:
                os.environ.pop("PADDLEX_DISABLE_AUTO_INIT", None)
            else:
                os.environ["PADDLEX_DISABLE_AUTO_INIT"] = old_env

    return wrapper


# バイナリ実行時の初期化を main.py から呼び出す関数
def initialize_for_binary() -> None:
    """バイナリ実行時用の初期化関数"""
    if not getattr(sys, "frozen", False):
        logger.debug("Not a binary execution, skipping binary initialization")
        return

    logger.info("Initializing PaddleX guard for binary execution")

    # バイナリ実行時のPaddleX設定を適用
    os.environ.setdefault("PADDLEX_DISABLE_AUTO_INIT", "1")
    os.environ.setdefault("PADDLEX_BINARY_MODE", "1")
    os.environ.setdefault("PADDLEX_CACHE_DISABLED", "1")

    if is_paddlex_available():
        ensure_paddlex_single_init()
        logger.info("PaddleX binary initialization completed")
    else:
        logger.debug("PaddleX not available in binary, initialization skipped")
