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
    """Issue #207対応: PaddleXは明示的に無効化"""
    return False  # paddlexを完全に無効化


def get_paddlex_init_status() -> dict:
    """PaddleX初期化状態を取得（デバッグ用）"""
    return {
        "paddlex_available": is_paddlex_available(),
        "paddlex_initialized": _paddlex_initialized,
        "is_frozen": getattr(sys, "frozen", False),
        "is_binary": hasattr(sys, "_MEIPASS"),
    }


def ensure_paddlex_single_init() -> None:
    """PaddleXの単一初期化を保証（環境変数設定後に呼び出すこと）"""
    global _paddlex_initialized, _paddlex_module

    if not is_paddlex_available():
        logger.debug("PaddleX not available, skipping initialization guard")
        return

    with _paddlex_init_lock:
        if _paddlex_initialized:
            logger.debug("PaddleX already initialized, skipping")
            return

        try:
            # 既存の環境変数を尊重し、設定されていない場合のみデフォルト値を設定
            os.environ.setdefault("PADDLEX_DISABLE_AUTO_INIT", "1")
            os.environ.setdefault("PADDLEX_INIT_MODE", "manual")

            # バイナリ実行時の特別な設定（既に設定済みの場合は変更しない）
            if getattr(sys, "frozen", False):
                logger.info("Binary execution detected, respecting pre-configured environment")
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

            # 環境変数の状態をログ出力（デバッグ用）
            env_status = {
                "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "PADDLE_CPU_ONLY": os.environ.get("PADDLE_CPU_ONLY"),
                "PADDLEX_DISABLE_AUTO_INIT": os.environ.get("PADDLEX_DISABLE_AUTO_INIT"),
            }
            logger.info(f"Initializing PaddleX with environment: {env_status}")

            # 手動初期化（必要な場合のみ）
            if hasattr(paddlex, "initialize") and not _paddlex_initialized:
                logger.info("Initializing PaddleX manually with pre-configured environment")
                paddlex.initialize()

            _paddlex_initialized = True
            logger.info("PaddleX initialization guard successful")

        except ImportError as e:
            logger.error(f"PaddleX import failed: {e}")
            logger.info("This may be a temporary issue if PaddleX is being installed")
            logger.warning("PaddleX initialization failed, retry will be allowed on next attempt")
            raise
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"PaddleX initialization guard failed ({error_type}): {e}")

            # 環境変数の状態を診断情報として出力
            env_diagnosis = {
                "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "NOT_SET"),
                "PADDLE_CPU_ONLY": os.environ.get("PADDLE_CPU_ONLY", "NOT_SET"),
                "PADDLEX_DISABLE_AUTO_INIT": os.environ.get("PADDLEX_DISABLE_AUTO_INIT", "NOT_SET"),
            }
            logger.error(f"Environment at failure: {env_diagnosis}")

            # 初期化に失敗した場合はフラグをFalseのままにして再試行を許可
            logger.warning("PaddleX initialization failed, retry will be allowed on next attempt")
            logger.info(
                "Possible solutions: 1) Ensure environment variables are set properly, "
                "2) Call force_paddlex_retry() to reset state, 3) Check PaddleX installation"
            )
            raise


def safe_paddlex_import() -> Optional[Any]:
    """安全なPaddleXインポート（重複初期化防止付き）"""
    if not is_paddlex_available():
        return None

    ensure_paddlex_single_init()
    return _paddlex_module


def reset_paddlex_state() -> None:
    """PaddleX状態をリセット（テスト用および失敗後の再試行用）"""
    global _paddlex_initialized, _paddlex_module
    with _paddlex_init_lock:
        _paddlex_initialized = False
        _paddlex_module = None
        logger.debug("PaddleX state reset - retry will be allowed")


def force_paddlex_retry() -> None:
    """PaddleX初期化の再試行を強制的に許可（失敗後のリカバリ用）"""
    global _paddlex_initialized
    with _paddlex_init_lock:
        if _paddlex_initialized:
            logger.info("Forcing PaddleX initialization retry after previous failure")
            _paddlex_initialized = False


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


# バイナリ実行時の環境設定を main.py から呼び出す関数
def setup_paddlex_environment_for_binary() -> None:
    """バイナリ実行時用の環境設定関数（初期化は行わない）"""
    if not getattr(sys, "frozen", False):
        logger.debug("Not a binary execution, skipping binary environment setup")
        return

    logger.info("Setting up PaddleX environment for binary execution")

    # バイナリ実行時のPaddleX環境設定を適用（初期化はしない）
    os.environ.setdefault("PADDLEX_DISABLE_AUTO_INIT", "1")
    os.environ.setdefault("PADDLEX_BINARY_MODE", "1")
    os.environ.setdefault("PADDLEX_CACHE_DISABLED", "1")

    # 基本的なCPU専用設定も事前に適用
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    os.environ.setdefault("PADDLE_CPU_ONLY", "1")
    os.environ.setdefault("PADDLE_SKIP_GPU_MEMORY_INIT", "1")

    logger.info("PaddleX binary environment setup completed (initialization deferred)")


def initialize_for_binary() -> None:
    """バイナリ実行時用の初期化関数（後方互換性のため残す）"""
    logger.warning(
        "initialize_for_binary() is deprecated, use setup_paddlex_environment_for_binary() instead"
    )
    setup_paddlex_environment_for_binary()

    if is_paddlex_available():
        ensure_paddlex_single_init()
        logger.info("PaddleX binary initialization completed")
    else:
        logger.debug("PaddleX not available in binary, initialization skipped")
