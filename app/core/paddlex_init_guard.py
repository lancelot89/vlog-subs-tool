"""
PaddleOCR初期化ガード - バイナリ実行時の重複初期化を防止

Issue #207 対応: PaddleOCRのcpp_extension問題を解決（PaddleXは使用しない）
"""

import functools
import logging
import os
import sys
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# グローバル状態管理
_paddleocr_initialized = False
_paddleocr_init_lock = threading.Lock()
_binary_init_complete = False  # バイナリ実行時の初期化完了フラグ


def is_paddleocr_available() -> bool:
    """PaddleOCRが利用可能かどうかを確認"""
    try:
        import importlib.util

        return importlib.util.find_spec("paddleocr") is not None
    except ImportError:
        return False


def get_paddleocr_init_status() -> dict:
    """PaddleOCR初期化状態を取得（デバッグ用）"""
    return {
        "paddleocr_available": is_paddleocr_available(),
        "paddleocr_initialized": _paddleocr_initialized,
        "is_frozen": getattr(sys, "frozen", False),
        "is_binary": hasattr(sys, "_MEIPASS"),
        "binary_init_complete": _binary_init_complete,
    }


def ensure_paddleocr_cpp_extension_safe() -> None:
    """PaddleOCRのcpp_extension問題を解決（Issue #207対応）"""
    global _paddleocr_initialized

    if not is_paddleocr_available():
        logger.debug("PaddleOCR not available, skipping cpp_extension guard")
        return

    with _paddleocr_init_lock:
        if _paddleocr_initialized:
            logger.debug("PaddleOCR cpp_extension already patched, skipping")
            return

        try:
            # バイナリ実行時の追加設定
            if getattr(sys, "frozen", False):
                logger.info("Binary execution detected - applying Issue #207 cpp_extension workaround")
                # cpp_extension問題を回避
                os.environ.setdefault("PADDLE_SKIP_CUDA_COMPILER_CHECK", "1")
                os.environ.setdefault("PADDLE_DISABLE_CPP_EXTENSION", "1")

            # PaddleX初期化制御（Issue #207: 必要最小限の制御）
            os.environ.setdefault("PADDLEX_DISABLE_AUTO_INIT", "1")

            # バイナリ実行時のみPaddleXキャッシュ無効化
            if getattr(sys, "frozen", False):
                os.environ.setdefault("PADDLEX_CACHE_DISABLED", "1")

            # cpp_extension.load のモンキーパッチ
            def stub_cpp_extension_load(*args, **kwargs):
                logger.warning("cpp_extension.load() called - returning stub to prevent crash")
                from unittest.mock import Mock
                return Mock()

            # PaddleOCRインポート前にcpp_extensionをパッチ
            try:
                import paddle.utils.cpp_extension
                original_load = getattr(paddle.utils.cpp_extension, 'load', None)
                if original_load:
                    paddle.utils.cpp_extension.load = stub_cpp_extension_load
                    logger.info("Applied cpp_extension.load patch for Issue #207")
            except ImportError:
                logger.debug("paddle.utils.cpp_extension not available for patching")

            # 環境変数の状態をログ出力
            env_status = {
                "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "PADDLE_CPU_ONLY": os.environ.get("PADDLE_CPU_ONLY"),
                "PADDLE_DISABLE_CPP_EXTENSION": os.environ.get("PADDLE_DISABLE_CPP_EXTENSION"),
                "PADDLEX_DISABLE": os.environ.get("PADDLEX_DISABLE"),
            }
            logger.info(f"PaddleOCR cpp_extension guard applied with environment: {env_status}")

            _paddleocr_initialized = True

        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"PaddleOCR cpp_extension guard failed ({error_type}): {e}")

            # 環境変数の状態を診断情報として出力
            env_diagnosis = {
                "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "NOT_SET"),
                "PADDLE_CPU_ONLY": os.environ.get("PADDLE_CPU_ONLY", "NOT_SET"),
                "PADDLE_DISABLE_CPP_EXTENSION": os.environ.get("PADDLE_DISABLE_CPP_EXTENSION", "NOT_SET"),
                "PADDLEX_DISABLE": os.environ.get("PADDLEX_DISABLE", "NOT_SET"),
            }
            logger.error(f"Environment at failure: {env_diagnosis}")
            raise


def safe_paddleocr_import() -> None:
    """安全なPaddleOCRインポート（cpp_extension問題回避付き）"""
    if not is_paddleocr_available():
        logger.warning("PaddleOCR not available")
        return

    ensure_paddleocr_cpp_extension_safe()


def reset_paddleocr_state() -> None:
    """PaddleOCR状態をリセット（テスト用および失敗後の再試行用）"""
    global _paddleocr_initialized
    with _paddleocr_init_lock:
        _paddleocr_initialized = False
        logger.debug("PaddleOCR state reset - retry will be allowed")


def prevent_cpp_extension_crash(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    デコレータ: cpp_extensionクラッシュを防止
    PaddleOCR使用前に適用することでcpp_extension問題を回避
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # 事前にcpp_extension安全化を実行
        if is_paddleocr_available():
            ensure_paddleocr_cpp_extension_safe()

        result = func(*args, **kwargs)
        return result

    return wrapper


# バイナリ実行時の環境設定を main.py から呼び出す関数
def setup_paddleocr_environment_for_binary() -> None:
    """バイナリ実行時用のPaddleOCR環境設定関数"""
    if not getattr(sys, "frozen", False):
        logger.debug("Not a binary execution, skipping binary environment setup")
        return

    logger.info("Setting up PaddleOCR environment for binary execution")

    # Issue #207対応: cpp_extension問題を回避
    os.environ.setdefault("PADDLE_SKIP_CUDA_COMPILER_CHECK", "1")
    os.environ.setdefault("PADDLE_DISABLE_CPP_EXTENSION", "1")

    # PaddleX初期化制御（PaddleOCRとの互換性を保持）
    os.environ.setdefault("PADDLEX_DISABLE_AUTO_INIT", "1")
    os.environ.setdefault("PADDLEX_CACHE_DISABLED", "1")

    # 基本的なCPU専用設定も事前に適用
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    os.environ.setdefault("PADDLE_CPU_ONLY", "1")
    os.environ.setdefault("PADDLE_SKIP_GPU_MEMORY_INIT", "1")

    logger.info("PaddleOCR binary environment setup completed")


def complete_binary_initialization() -> None:
    """バイナリ初期化完了をマーク"""
    global _binary_init_complete
    if getattr(sys, "frozen", False):
        _binary_init_complete = True
        logger.info("Binary initialization marked as complete")
