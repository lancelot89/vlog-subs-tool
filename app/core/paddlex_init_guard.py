"""Runtime guards for PaddleOCR/PaddleX in frozen binaries.

The application relies on PaddleOCR and PaddleX to perform OCR inference.
Frozen binaries produced by PyInstaller need a few adjustments so that
Paddle's optional C++ extension loader does not attempt to build custom
operators and so that runtime environments fail fast when required modules
are missing.  This module centralises those safeguards and exposes helpers
that other parts of the application can call before interacting with the
OCR stack.
"""

import contextlib
import functools
import importlib
import importlib.util
import logging
import os
import sys
import tempfile
import threading
import types
from typing import Any, Callable, Optional, Sequence

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


def verify_paddle_runtime_dependencies(
    modules: Optional[Sequence[str]] = None,
) -> None:
    """Ensure critical Paddle modules can be imported.

    Parameters
    ----------
    modules:
        Optional explicit list of module names to validate.  When ``None`` the
        default list (``paddle``, ``paddleocr`` and ``paddlex``) is used.

    Raises
    ------
    ModuleNotFoundError
        If any of the required modules cannot be imported.  The exception
        message contains the per-module error details to help with debugging
        missing runtime dependencies inside frozen binaries.
    """

    modules = modules or ("paddle", "paddleocr", "paddlex")
    failures = []

    for module_name in modules:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.error("Required module import failed: %s (%s)", module_name, exc)
            failures.append((module_name, exc))
        else:
            logger.debug("Verified import for module: %s", module_name)

    if failures:
        summary = ", ".join(f"{name}: {error}" for name, error in failures)
        raise ModuleNotFoundError(
            "Failed to import required Paddle modules. "
            f"Please ensure the runtime includes paddlepaddle, paddleocr and paddlex. "
            f"Details: {summary}"
        )


def _populate_cpp_extension_stub(module: types.ModuleType) -> types.ModuleType:
    """Install a lightweight stub for :mod:`paddle.utils.cpp_extension`.

    When PaddleOCR imports :mod:`paddle`, the package eagerly imports
    ``paddle.utils.cpp_extension`` which in turn probes the local compiler tool
    chain (``ccache``/``cl.exe``/``nvcc``).  PyInstaller bundles do not ship
    with these developer tools and the probing step emits warnings and, on
    Windows, may attempt to spawn subprocesses that fail outright.  The
    application only relies on Paddle's high level Python APIs, therefore the
    extension machinery can be replaced with a minimal stub that exposes the
    expected attributes while short‑circuiting any build logic.
    """

    if getattr(module, "_vst_cpp_extension_stub", False):
        return module

    module.__file__ = getattr(module, "__file__", "vlog-subs-tool:paddle_cpp_extension_stub.py")
    module.__package__ = "paddle.utils"
    module.__path__ = []  # Mark as package so submodule imports succeed
    module._vst_cpp_extension_stub = True  # type: ignore[attr-defined]

    class _DisabledExtension:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover -
            self.args = args
            self.kwargs = kwargs

    class _DisabledBuildExtension:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover -
            self.args = args
            self.kwargs = kwargs

        def build_extensions(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover -
            return None

    def _log_stubbed(name: str) -> Callable[..., Any]:
        def _inner(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover -
            logger.debug("paddle.utils.cpp_extension.%s() stubbed in frozen build", name)
            return None

        return _inner

    def _stub_normalize(kwargs: Any, use_cuda: bool = False) -> Any:  # pragma: no cover -
        logger.debug("normalize_extension_kwargs() stubbed in frozen build")
        return kwargs

    def _stub_load(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover -
        logger.debug("Skipping paddle.utils.cpp_extension.load() in frozen build")
        return types.SimpleNamespace()

    module.CppExtension = _DisabledExtension  # type: ignore[attr-defined]
    module.CUDAExtension = _DisabledExtension  # type: ignore[attr-defined]
    module.BuildExtension = _DisabledBuildExtension  # type: ignore[attr-defined]
    module.setup = _log_stubbed("setup")  # type: ignore[attr-defined]
    module.load = _stub_load  # type: ignore[attr-defined]
    module.get_build_directory = lambda *args, **kwargs: os.path.join(  # type: ignore[attr-defined]
        tempfile.gettempdir(), "paddle_cpp_extensions"
    )
    module.load_op_meta_info_and_register_op = _log_stubbed("load_op_meta_info_and_register_op")  # type: ignore[attr-defined]
    module.parse_op_info = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    module.normalize_extension_kwargs = _stub_normalize  # type: ignore[attr-defined]
    module.bootstrap_context = contextlib.nullcontext  # type: ignore[attr-defined]
    module.add_compile_flag = _log_stubbed("add_compile_flag")  # type: ignore[attr-defined]
    module.clean_object_if_change_cflags = _log_stubbed("clean_object_if_change_cflags")  # type: ignore[attr-defined]
    module.check_abi_compatibility = _log_stubbed("check_abi_compatibility")  # type: ignore[attr-defined]
    module.log_v = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    module.find_ccache_home = lambda: None  # type: ignore[attr-defined]
    module.find_cuda_home = lambda: None  # type: ignore[attr-defined]
    module.find_rocm_home = lambda: None  # type: ignore[attr-defined]
    module.IS_WINDOWS = sys.platform.startswith("win")  # type: ignore[attr-defined]
    module.OS_NAME = os.name  # type: ignore[attr-defined]
    module.MSVC_COMPILE_FLAGS = []  # type: ignore[attr-defined]
    module.CLANG_COMPILE_FLAGS = []  # type: ignore[attr-defined]
    module.CLANG_LINK_FLAGS = []  # type: ignore[attr-defined]
    module.CCACHE_HOME = None  # type: ignore[attr-defined]
    module.__all__ = [  # type: ignore[attr-defined]
        "CppExtension",
        "CUDAExtension",
        "BuildExtension",
        "load",
        "setup",
        "get_build_directory",
        "load_op_meta_info_and_register_op",
        "parse_op_info",
    ]

    def _module_getattr(name: str) -> Any:  # pragma: no cover - defensive fallback
        logger.debug("Providing dynamic stub for paddle.utils.cpp_extension.%s", name)
        return _log_stubbed(name)

    module.__getattr__ = _module_getattr  # type: ignore[method-assign]
    module.cpp_extension = module  # type: ignore[attr-defined]
    module.extension_utils = module  # type: ignore[attr-defined]
    return module


def _install_cpp_extension_stub() -> None:
    module_name = "paddle.utils.cpp_extension"
    existing = sys.modules.get(module_name)

    if existing is None:
        existing = types.ModuleType(module_name)
        sys.modules[module_name] = existing
        logger.info("Installed Paddle cpp_extension stub for frozen runtime")
    else:
        logger.info("Reusing pre-imported Paddle cpp_extension module with stub")

    stub = _populate_cpp_extension_stub(existing)

    for alias in (
        f"{module_name}.cpp_extension",
        f"{module_name}.extension_utils",
    ):
        sys.modules[alias] = stub


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
                logger.info(
                    "Binary execution detected - applying Issue #207 cpp_extension workaround"
                )
                # cpp_extension問題を回避
                os.environ.setdefault("PADDLE_SKIP_CUDA_COMPILER_CHECK", "1")
                os.environ.setdefault("PADDLE_DISABLE_CPP_EXTENSION", "1")

            # cpp_extension.load のモンキーパッチ
            def stub_cpp_extension_load(*args: Any, **kwargs: Any) -> Any:
                logger.warning("cpp_extension.load() called - returning stub to prevent crash")
                from unittest.mock import Mock

                return Mock()

            # PaddleOCRインポート前にcpp_extensionをパッチ
            try:
                import paddle.utils.cpp_extension

                original_load = getattr(paddle.utils.cpp_extension, "load", None)
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
                "PADDLE_DISABLE_CPP_EXTENSION": os.environ.get(
                    "PADDLE_DISABLE_CPP_EXTENSION", "NOT_SET"
                ),
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

    # PyInstallerバイナリではcpp_extensionをスタブ化してビルドツール探索を防止
    _install_cpp_extension_stub()

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
