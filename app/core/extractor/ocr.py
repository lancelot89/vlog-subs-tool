"""PaddleOCR integration helpers used by the subtitle extractor.

The original implementation eagerly pushed raw video frame data directly into
``PaddleOCR.ocr``.  When large batches of frames or full-resolution frames were
handed over, PaddleOCR attempted to allocate huge intermediate buffers and the
process crashed with ``std::bad_alloc``/``malloc`` failures.  This module now
wraps PaddleOCR with a thin safety layer that:

* Detects whether PaddleOCR/PaddleX are importable and exposes availability
  flags so the UI can react gracefully when the dependency is missing.
* Converts legacy PaddleOCR constructor arguments to the new v3 API while
  stripping unsupported parameters.
* Provides a model cache helper that understands the default PaddleOCR cache
  location.
* Normalises video frame inputs (``numpy.ndarray`` / ``VideoFrame`` /
  dictionaries containing an ``image`` key), resizes overly large frames and
  splits large iterables into small batches before invoking PaddleOCR.

These changes make it safe to feed video sampling metadata into the OCR engine
without exhausting memory, satisfying the regression tests bundled with the
repository.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import multiprocessing
import os
import pickle
import platform
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import cv2
import numpy as np

from app.core.cpu_profiler import get_adaptive_thread_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flags --------------------------------------------------------
# ---------------------------------------------------------------------------
try:  # pragma: no cover - availability detection
    from paddleocr import PaddleOCR

    PADDLEOCR_AVAILABLE = True
    _PADDLE_IMPORT_ERROR: Optional[Exception] = None
except Exception as _import_error:  # pragma: no cover - dependency missing
    PaddleOCR = None
    PADDLEOCR_AVAILABLE = False
    _PADDLE_IMPORT_ERROR = _import_error

PADDLEX_AVAILABLE = importlib.util.find_spec("paddlex") is not None
_PADDLEX_MODULE: Optional[Any] = None


def _load_paddlex_module() -> Any:
    """Lazily import :mod:`paddlex` when it is actually required."""

    if not PADDLEX_AVAILABLE:  # pragma: no cover - optional dependency missing
        raise ModuleNotFoundError("paddlex is not available")

    global _PADDLEX_MODULE
    if _PADDLEX_MODULE is None:  # pragma: no cover - import happens on demand
        _PADDLEX_MODULE = importlib.import_module("paddlex")
    return _PADDLEX_MODULE


# ---------------------------------------------------------------------------
# Legacy helpers - now replaced by cpu_profiler module ---------------------
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helper data structures ----------------------------------------------------
# ---------------------------------------------------------------------------


@dataclass
class OCRResult:
    """Container for a single OCR detection."""

    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, w, h


@dataclass
class OCRStageTimings:
    """Container for stage-by-stage OCR timing measurements."""

    decode_time: float = 0.0  # Video frame decoding/preprocessing time
    detection_time: float = 0.0  # Text detection time
    classification_time: float = 0.0  # Text orientation classification time
    recognition_time: float = 0.0  # Text recognition time
    total_time: float = 0.0  # Total OCR processing time

    def log_summary(self, platform_info: str = "") -> None:
        """Log a summary of timing measurements."""
        platform_suffix = f" on {platform_info}" if platform_info else ""

        # Determine if we have actual stage measurements or fallback data
        has_actual_stages = self.detection_time > 0 and self.classification_time >= 0
        measurement_type = "Actual" if has_actual_stages else "Fallback"

        logger.info("OCR Stage Timings (%s)%s:", measurement_type, platform_suffix)
        logger.info("  Decode/Preprocess: %.3f ms", self.decode_time * 1000)

        if has_actual_stages:
            logger.info("  Text Detection:    %.3f ms (measured)", self.detection_time * 1000)
            logger.info(
                "  Text Classification: %.3f ms (measured)", self.classification_time * 1000
            )
            logger.info("  Text Recognition:  %.3f ms (measured)", self.recognition_time * 1000)
        else:
            logger.info("  Text Detection:    %.3f ms (not measured)", self.detection_time * 1000)
            logger.info(
                "  Text Classification: %.3f ms (not measured)", self.classification_time * 1000
            )
            logger.info(
                "  Text Recognition:  %.3f ms (total OCR fallback)", self.recognition_time * 1000
            )

        logger.info("  Total OCR Time:    %.3f ms", self.total_time * 1000)

        if self.total_time > 0 and has_actual_stages:
            logger.info("Stage Breakdown:")
            logger.info("  Decode:    %.1f%%", (self.decode_time / self.total_time) * 100)
            logger.info("  Detection: %.1f%%", (self.detection_time / self.total_time) * 100)
            logger.info(
                "  Classification: %.1f%%", (self.classification_time / self.total_time) * 100
            )
            logger.info("  Recognition: %.1f%%", (self.recognition_time / self.total_time) * 100)
        elif not has_actual_stages:
            logger.info("Stage breakdown not available (using fallback measurement)")


# ---------------------------------------------------------------------------
# PaddleOCR parameter helpers ----------------------------------------------
# ---------------------------------------------------------------------------


def _create_safe_paddleocr_kwargs(original: Mapping[str, Any]) -> Dict[str, Any]:
    """Sanitise PaddleOCR constructor arguments.

    The PaddleOCR 3.x API deprecated a couple of parameters that were still
    passed by the legacy implementation (`use_angle_cls`, `show_log`,
    `use_space_char`, `drop_score`).  Passing them verbatim raises runtime
    errors, so this helper converts or drops them as needed while preserving the
    rest of the mapping unchanged.
    """

    safe: Dict[str, Any] = {}
    for key, value in original.items():
        if key == "use_angle_cls":
            # PaddleOCR >= 3.0 renamed the flag to use_textline_orientation.
            safe["use_textline_orientation"] = bool(value)
        elif key in {"show_log", "use_space_char", "use_gpu", "max_text_length"}:
            # No longer accepted by the constructor – ignore silently.
            continue
        elif key == "drop_score":
            # Newer versions expose the same behaviour via text_rec_score_thresh.
            safe["text_rec_score_thresh"] = value
        else:
            safe[key] = value
    return safe


class OCRModelDownloader:
    """Utility helpers around the PaddleOCR cache directory."""

    @staticmethod
    def get_paddleocr_cache_dir() -> Path:
        """Return the default PaddleOCR cache directory (``~/.paddleocr``)."""

        return Path.home() / ".paddleocr"

    @staticmethod
    def is_paddleocr_model_available() -> bool:
        """Heuristic check for locally cached PaddleOCR models.

        PaddleOCR stores downloaded models underneath ``~/.paddleocr``.  The
        exact layout differs between releases, therefore we simply check for the
        presence of a handful of well-known directories.
        """

        cache_dir = OCRModelDownloader.get_paddleocr_cache_dir()
        if not cache_dir.exists():
            return False

        expected_names = {
            "det",
            "rec",
            "inference",
            "pretrained",
            "whl",
            "text_detection",
            "text_recognition",
        }
        for child in cache_dir.iterdir():
            if child.is_dir() and child.name.lower() in expected_names:
                return True
        return False


# ---------------------------------------------------------------------------
# Simple PaddleOCR wrapper --------------------------------------------------
# ---------------------------------------------------------------------------


class SimplePaddleOCREngine:
    """Small, memory-safe PaddleOCR wrapper used throughout the app."""

    def __init__(
        self,
        language: str = "ja",
        confidence_threshold: float = 0.7,
        models_root: Optional[Path] = None,
        *,
        max_batch_size: int = 4,
        max_image_pixels: int = 4096 * 4096,
        max_side_length: int = 4096,
    ) -> None:
        self.language = language
        self.confidence_threshold = confidence_threshold
        self.models_root = Path(models_root) if models_root else None
        self.max_batch_size = max(1, int(max_batch_size))
        self.max_image_pixels = int(max_image_pixels)
        self.max_side_length = int(max_side_length)

        self._ocr: Optional[Any] = None
        self._enable_stage_timing: bool = False
        self._last_timing_results: Optional[OCRStageTimings] = None

    # ----------------------- model path helpers -----------------------
    def _resolve_models_root(self) -> Path:
        """Resolve the directory that contains bundled PaddleOCR models."""

        # 1) explicit path supplied during construction
        if self.models_root is not None:
            det_dir = self.models_root / "PP-OCRv5_server_det"
            rec_dir = self.models_root / "PP-OCRv5_server_rec"
            if det_dir.exists() and rec_dir.exists():
                logger.debug("Using explicit PaddleOCR model directory: %s", self.models_root)
                return self.models_root

        # 2) environment variable override
        env_dir = os.environ.get("PADDLE_MODELS_DIR")
        if env_dir:
            try:
                env_path = Path(env_dir).resolve()
                det_dir = env_path / "PP-OCRv5_server_det"
                rec_dir = env_path / "PP-OCRv5_server_rec"
                if det_dir.exists() and rec_dir.exists():
                    logger.debug("Using PADDLE_MODELS_DIR override: %s", env_path)
                    return env_path
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Invalid PADDLE_MODELS_DIR '%s': %s", env_dir, exc)

        # 3) look for app/models/paddleocr relative to this file
        here = Path(__file__).resolve()
        for parent in [here.parent] + list(here.parents)[:6]:
            candidate = parent / "app" / "models" / "paddleocr"
            det_dir = candidate / "PP-OCRv5_server_det"
            rec_dir = candidate / "PP-OCRv5_server_rec"
            if det_dir.exists() and rec_dir.exists():
                logger.debug("Found PaddleOCR models under %s", candidate)
                return candidate

        # 4) fallback to cwd/app/models/paddleocr
        cwd_candidate = Path.cwd() / "app" / "models" / "paddleocr"
        det_dir = cwd_candidate / "PP-OCRv5_server_det"
        rec_dir = cwd_candidate / "PP-OCRv5_server_rec"
        if det_dir.exists() and rec_dir.exists():
            logger.debug("Using models from working directory: %s", cwd_candidate)
            return cwd_candidate

        # 5) additional Windows specific checks (frozen app, AppData)
        if platform.system() == "Windows":  # pragma: no cover - platform specific
            if getattr(sys, "frozen", False):
                frozen_dir = Path(sys.executable).parent / "app" / "models" / "paddleocr"
                det_dir = frozen_dir / "PP-OCRv5_server_det"
                rec_dir = frozen_dir / "PP-OCRv5_server_rec"
                if det_dir.exists() and rec_dir.exists():
                    logger.debug("Found models in frozen application directory: %s", frozen_dir)
                    return frozen_dir

            appdata = os.environ.get("APPDATA")
            if appdata:
                appdata_dir = Path(appdata) / "vlog-subs-tool" / "models" / "paddleocr"
                det_dir = appdata_dir / "PP-OCRv5_server_det"
                rec_dir = appdata_dir / "PP-OCRv5_server_rec"
                if det_dir.exists() and rec_dir.exists():
                    logger.debug("Found models in AppData: %s", appdata_dir)
                    return appdata_dir

        raise FileNotFoundError(
            "Bundled PaddleOCR models not found. Expected app/models/paddleocr "
            "containing PP-OCRv5_server_det and PP-OCRv5_server_rec."
        )

    # ----------------------- initialisation ---------------------------
    def initialize(self) -> bool:
        """Initialise PaddleOCR using bundled models.

        Returns ``True`` on success and ``False`` if PaddleOCR could not be
        initialised.  Errors are logged with additional platform information.
        """

        if self._ocr is not None:
            return True

        if PaddleOCR is None and not PADDLEOCR_AVAILABLE:
            logger.error("PaddleOCR import failed: %s", _PADDLE_IMPORT_ERROR)
            return False

        # Apply conservative environment defaults to keep memory usage under
        # control and make the CPU-only configuration explicit.
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
        os.environ.setdefault("FLAGS_call_stack_level", "2")

        # Use adaptive CPU profiling for optimal performance across all platforms
        try:
            thread_config = get_adaptive_thread_config()

            # Apply the optimized environment variables
            env_vars = thread_config.to_env_vars()
            for key, value in env_vars.items():
                os.environ.setdefault(key, value)

            # Platform-specific additional optimizations
            if platform.system() == "Darwin" and platform.machine() == "arm64":
                # Apple Silicon additional tweaks
                os.environ.setdefault("PADDLE_CPU_ONLY", "1")
                os.environ.setdefault("BLAS", "Accelerate")  # Prefer Apple Accelerate framework
                os.environ.setdefault(
                    "FLAGS_use_mkldnn", "false"
                )  # Disable MKLDNN on Apple Silicon
                os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
                logger.debug("Applied Apple Silicon specific PaddleOCR environment tweaks")

            elif platform.system() == "Windows":
                # Windows additional tweaks for stability
                os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
                os.environ.setdefault("PADDLE_CPU_ONLY", "1")
                os.environ.setdefault("PYTHONPATH", "")
                os.environ.setdefault("PADDLE_SKIP_GPU_MEMORY_INIT", "1")
                os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
                logger.debug("Applied Windows stability tweaks")

            logger.info("Applied adaptive CPU optimization: %s", thread_config)

        except Exception as e:
            logger.warning("Failed to apply adaptive CPU optimization, using fallback: %s", e)
            # Fallback to basic configuration
            os.environ.setdefault("OMP_NUM_THREADS", "2")
            os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

        try:
            models_root = self._resolve_models_root()
            det_dir = models_root / "PP-OCRv5_server_det"
            rec_dir = models_root / "PP-OCRv5_server_rec"

            if not det_dir.exists() or not rec_dir.exists():
                raise FileNotFoundError(f"Model directories not found: {det_dir}, {rec_dir}")

            lang = (
                "japan"
                if self.language.lower() in {"ja", "jpn", "japanese", "japan"}
                else self.language
            )

            # Cross-platform progressive configuration based on CPU profile
            is_windows = platform.system() == "Windows"

            # Get CPU profile for intelligent configuration selection
            try:
                from app.core.cpu_profiler import CPUProfiler

                profiler = CPUProfiler()
                cpu_profile = profiler.detect_cpu_profile()

                # Determine if we can use aggressive optimization based on CPU profile
                vendor = cpu_profile.get("vendor", "Unknown")
                generation = cpu_profile.get("generation")
                architecture = cpu_profile.get("architecture", "Unknown")

                use_aggressive = (
                    (
                        vendor == "Intel" and generation and generation >= 8
                    )  # 8th gen以降（Coffee Lake+）
                    or (vendor == "AMD" and generation and generation >= 2)  # Zen2+
                    or (vendor == "Apple")
                )

                logger.debug(
                    "CPU Profile: %s %s gen %s, using aggressive: %s",
                    vendor,
                    architecture,
                    generation,
                    use_aggressive,
                )

            except Exception as e:
                logger.warning("Failed to get CPU profile for configuration selection: %s", e)
                use_aggressive = False

            if is_windows:
                # Windows環境では段階的に性能向上設定を試行
                config_candidates = [
                    # Phase 1: 積極的性能最適化 (新しいCPU向け)
                    (
                        {
                            "text_detection_model_dir": str(det_dir.resolve()),
                            "text_recognition_model_dir": str(rec_dir.resolve()),
                            "lang": lang,
                            "use_textline_orientation": True,  # 角度検出有効化
                            "use_gpu": False,
                            "use_space_char": True,
                            "drop_score": 0.5,
                            "enable_mkldnn": True,  # MKL-DNN有効化
                        }
                        if use_aggressive
                        else None
                    ),
                    # Phase 2: 中程度の最適化
                    {
                        "text_detection_model_dir": str(det_dir.resolve()),
                        "text_recognition_model_dir": str(rec_dir.resolve()),
                        "lang": lang,
                        "use_textline_orientation": False,
                        "use_gpu": False,
                        "use_space_char": True,
                        "drop_score": 0.5,
                        "enable_mkldnn": True,  # MKL-DNN有効化のみ
                    },
                    # Phase 3: 安全設定 (従来の設定)
                    {
                        "text_detection_model_dir": str(det_dir.resolve()),
                        "text_recognition_model_dir": str(rec_dir.resolve()),
                        "lang": lang,
                        "use_textline_orientation": False,
                        "use_gpu": False,
                        "use_space_char": True,
                        "drop_score": 0.5,
                        "enable_mkldnn": False,
                    },
                    # Phase 4: Legacy API fallback
                    {
                        "det_model_dir": str(det_dir.resolve()),
                        "rec_model_dir": str(rec_dir.resolve()),
                        "lang": lang,
                        "use_angle_cls": False,
                        "use_gpu": False,
                        "enable_mkldnn": False,
                    },
                ]
                # Remove None entries
                config_candidates = [config for config in config_candidates if config is not None]
            else:
                # 非Windows環境では従来の設定
                config_candidates = [
                    {
                        "text_detection_model_dir": str(det_dir.resolve()),
                        "text_recognition_model_dir": str(rec_dir.resolve()),
                        "lang": lang,
                        "use_textline_orientation": True,
                        "use_gpu": False,
                    },
                    # Legacy API compatibility
                    {
                        "det_model_dir": str(det_dir.resolve()),
                        "rec_model_dir": str(rec_dir.resolve()),
                        "lang": lang,
                        "use_angle_cls": True,
                        "use_gpu": False,
                        "enable_mkldnn": True,
                    },
                    # Minimal parameters
                    {
                        "det_model_dir": str(det_dir.resolve()),
                        "rec_model_dir": str(rec_dir.resolve()),
                        "lang": lang,
                        "use_gpu": False,
                    },
                ]

            errors: List[str] = []
            for i, config in enumerate(config_candidates):
                kwargs = _create_safe_paddleocr_kwargs(config)
                try:
                    # Windows環境での段階的試行をログ出力
                    if is_windows:
                        phase_names = [
                            "Aggressive Performance",
                            "Moderate Optimization",
                            "Safe Configuration",
                            "Legacy Fallback",
                        ]
                        phase_name = phase_names[min(i, len(phase_names) - 1)]
                        logger.info("Trying Windows %s configuration...", phase_name)

                    logger.debug(
                        "Initialising PaddleOCR on %s with kwargs=%s",
                        platform.system(),
                        kwargs,
                    )
                    self._ocr = PaddleOCR(**kwargs)
                    if self._ocr is None:
                        raise RuntimeError("PaddleOCR returned None instance")

                    success_msg = f"PaddleOCR initialised successfully on {platform.system()}"
                    if is_windows and i < len(phase_names):
                        success_msg += f" using {phase_names[i]}"
                    success_msg += f" with features: {', '.join(sorted(kwargs.keys()))}"
                    logger.info(success_msg)
                    return True
                except Exception as exc:  # pragma: no cover - exercised via tests
                    error_msg = f"{type(exc).__name__}: {exc}"
                    errors.append(error_msg)
                    if is_windows:
                        logger.warning("Windows optimization phase %d failed: %s", i + 1, exc)
                    else:
                        logger.warning(
                            "PaddleOCR initialisation failed (%s): %s",
                            platform.system(),
                            exc,
                        )
                    self._ocr = None
                    continue

            logger.error(
                "All PaddleOCR configurations failed on %s: %s",
                platform.system(),
                "; ".join(errors),
            )
            return False

        except FileNotFoundError as exc:
            logger.error("PaddleOCR model files not found on %s: %s", platform.system(), exc)
            self._ocr = None
            return False
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("PaddleOCR initialisation failed on %s: %s", platform.system(), exc)
            self._ocr = None
            return False

    # ----------------------- benchmark helpers -----------------------
    def enable_stage_timing(self, enable: bool = True) -> None:
        """Enable or disable stage-by-stage timing measurements for Issue #170."""
        self._enable_stage_timing = enable
        if enable:
            logger.info("Stage-by-stage OCR timing enabled for Windows/WSL comparison")
        else:
            logger.info("Stage-by-stage OCR timing disabled")

    def get_last_timing_results(self) -> Optional[OCRStageTimings]:
        """Get the timing results from the last OCR operation."""
        return self._last_timing_results

    # ----------------------- inference helpers -----------------------
    def extract_text(
        self, image_input: Union[np.ndarray, Mapping[str, Any], Sequence[Any], Any]
    ) -> List[OCRResult]:
        """Run OCR on the provided image or iterable of images.

        ``image_input`` may be a single ``numpy.ndarray``, a dataclass/dict that
        exposes an ``image`` attribute/key, or an iterable of such values.  When
        multiple frames are provided we automatically chunk them into batches to
        keep the working set small.
        """

        if self._ocr is None and not self.initialize():
            logger.error("OCR engine not initialised. Call initialize() first.")
            return []

        if isinstance(image_input, np.ndarray):
            return self._extract_from_single(image_input)

        if isinstance(image_input, Mapping):
            extracted = self._extract_image_array(image_input)
            return self._extract_from_single(extracted) if extracted is not None else []

        if isinstance(image_input, (str, bytes)):
            logger.warning("String input is not supported for OCR")
            return []

        if isinstance(image_input, Sequence):
            return self._extract_from_sequence(image_input)

        # Handle generic iterables (e.g. generators)
        if isinstance(image_input, Iterable):
            return self._extract_from_iterable(image_input)

        extracted = self._extract_image_array(image_input)
        if extracted is None:
            logger.warning("Unsupported image input type: %s", type(image_input))
            return []
        return self._extract_from_single(extracted)

    # ------------------------------------------------------------------
    def _extract_from_sequence(self, images: Sequence[Any]) -> List[OCRResult]:
        results: List[OCRResult] = []
        if not images:
            return results

        for batch in self._chunk_sequence(images, self.max_batch_size):
            results.extend(self._process_batch(batch))
        return results

    def _extract_from_iterable(self, images: Iterable[Any]) -> List[OCRResult]:
        results: List[OCRResult] = []
        batch: List[Any] = []
        for element in images:
            batch.append(element)
            if len(batch) >= self.max_batch_size:
                results.extend(self._process_batch(batch))
                batch.clear()
        if batch:
            results.extend(self._process_batch(batch))
        return results

    def _process_batch(self, batch: Sequence[Any]) -> List[OCRResult]:
        batch_results: List[OCRResult] = []
        for element in batch:
            array = self._extract_image_array(element)
            if array is None:
                continue
            batch_results.extend(self._extract_from_single(array))
        return batch_results

    @staticmethod
    def _chunk_sequence(seq: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
        for idx in range(0, len(seq), size):
            yield seq[idx : idx + size]

    def _extract_image_array(self, image_like: Any) -> Optional[np.ndarray]:
        if image_like is None:
            return None
        if isinstance(image_like, np.ndarray):
            return image_like

        # ``VideoFrame`` dataclass from ``sampler.py`` exposes ``image``.
        if hasattr(image_like, "image"):
            candidate = getattr(image_like, "image")
            if isinstance(candidate, np.ndarray):
                return candidate

        if isinstance(image_like, Mapping):
            for key in ("image", "frame", "data", "array"):
                value = image_like.get(key)
                if isinstance(value, np.ndarray):
                    return value
        return None

    def _preprocess_image(self, image: Any) -> Optional[np.ndarray]:
        if image is None:
            return None

        if not isinstance(image, np.ndarray):
            return None

        if image.size == 0:
            return None

        # 画像の基本的な形状チェック
        if image.ndim < 2 or image.ndim > 3:
            logger.warning(f"Invalid image dimensions: {image.ndim}, expected 2 or 3")
            return None

        # 画像サイズの初期チェック
        height, width = image.shape[:2]
        if height <= 0 or width <= 0:
            logger.warning(f"Invalid image size: {width}x{height}")
            return None

        # Ensure uint8 BGR format expected by PaddleOCR
        processed = image.copy()  # 元の画像を変更しないようにコピー

        try:
            if processed.dtype != np.uint8:
                processed = np.clip(processed, 0, 255).astype(np.uint8)

            # 色チャンネル数の安全なチェックと変換
            if processed.ndim == 2:
                processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
            elif processed.ndim == 3:
                if processed.shape[2] == 4:
                    processed = cv2.cvtColor(processed, cv2.COLOR_BGRA2BGR)
                elif processed.shape[2] == 1:
                    processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
                elif processed.shape[2] != 3:
                    logger.warning(f"Unsupported number of channels: {processed.shape[2]}")
                    return None
            else:
                logger.warning(f"Unexpected image format after conversion: {processed.shape}")
                return None

            # メモリレイアウトの確認と修正
            if not processed.flags.c_contiguous:
                processed = np.ascontiguousarray(processed)

            # 画像サイズの再確認
            height, width = processed.shape[:2]
            if height <= 0 or width <= 0:
                logger.warning(f"Invalid processed image size: {width}x{height}")
                return None

            # 極端に小さい画像のチェック
            if height < 10 or width < 10:
                logger.warning(f"Image too small for OCR: {width}x{height}")
                return None

            # ピクセル数制限の適用
            total_pixels = height * width
            if self.max_image_pixels > 0 and total_pixels > self.max_image_pixels:
                scale = (self.max_image_pixels / float(total_pixels)) ** 0.5
                new_w = max(10, int(width * scale))  # 最小サイズを保証
                new_h = max(10, int(height * scale))
                try:
                    processed = cv2.resize(processed, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    if processed is None or processed.size == 0:
                        logger.warning("Resize operation failed (max_pixels)")
                        return None
                    height, width = processed.shape[:2]
                except Exception as e:
                    logger.error(f"Failed to resize image (max_pixels): {e}")
                    return None

            # 最大辺長制限の適用
            if self.max_side_length > 0 and (
                height > self.max_side_length or width > self.max_side_length
            ):
                scale = min(
                    self.max_side_length / float(height),
                    self.max_side_length / float(width),
                )
                new_w = max(10, int(width * scale))  # 最小サイズを保証
                new_h = max(10, int(height * scale))
                try:
                    processed = cv2.resize(processed, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    if processed is None or processed.size == 0:
                        logger.warning("Resize operation failed (max_side)")
                        return None
                except Exception as e:
                    logger.error(f"Failed to resize image (max_side): {e}")
                    return None

            # 最終的な画像の検証
            if processed is None or processed.size == 0:
                logger.warning("Final processed image is invalid")
                return None

            final_height, final_width = processed.shape[:2]
            if final_height <= 0 or final_width <= 0:
                logger.warning(
                    f"Final processed image has invalid size: {final_width}x{final_height}"
                )
                return None

            if processed.ndim != 3 or processed.shape[2] != 3:
                logger.warning(f"Final processed image has invalid format: {processed.shape}")
                return None

            return processed

        except Exception as e:
            logger.error(f"Error during image preprocessing: {e}")
            return None

    def _extract_from_single(self, image: Optional[np.ndarray]) -> List[OCRResult]:
        if image is None:
            return []

        # Initialize timing measurements for Issue #170
        timing = OCRStageTimings() if self._enable_stage_timing else None
        overall_start_time = time.perf_counter() if timing else None

        # Stage 1: Decode/Preprocess
        decode_start_time = time.perf_counter() if timing else None
        processed = self._preprocess_image(image)
        if timing:
            timing.decode_time = time.perf_counter() - decode_start_time

        if processed is None:
            return []

        # OCR実行前の最終検証
        try:
            # processed is guaranteed to be np.ndarray here due to None check above

            if processed.size == 0:
                logger.warning("Processed image is empty")
                return []

            if processed.ndim != 3 or processed.shape[2] != 3:
                logger.warning(f"Invalid processed image format: {processed.shape}")
                return []

            # PaddleOCRに渡す前にメモリ整合性をチェック
            if not processed.flags.c_contiguous:
                logger.warning("Image is not contiguous, fixing...")
                processed = np.ascontiguousarray(processed)

            # 画像データの整合性チェック
            if not processed.data.contiguous:
                logger.warning("Image data is not contiguous")
                return []

            logger.debug(
                f"Sending image to OCR: shape={processed.shape}, dtype={processed.dtype}, contiguous={processed.flags.c_contiguous}"
            )

            # Stages 2-4: PaddleOCR execution with detailed timing
            ocr_start_time = time.perf_counter() if timing else None
            raw_results = self._run_ocr_with_timing(processed, timing, timeout_seconds=30)

        except IndexError as exc:
            # Windows環境でのvector<bool> subscriptエラーの特別処理
            if "vector" in str(exc) and "subscript" in str(exc):
                logger.warning(
                    "Windows-specific PaddleX vector error detected, skipping image: %s",
                    exc,
                )
                return []
            else:
                logger.error("PaddleOCR IndexError on %s: %s", platform.system(), exc)
                return []
        except TimeoutError as exc:
            logger.error("PaddleOCR timeout on %s: %s", platform.system(), exc)
            return []
        except (MemoryError, RuntimeError, ValueError) as exc:
            logger.error("PaddleOCR memory/runtime error on %s: %s", platform.system(), exc)
            return []
        except Exception as exc:  # pragma: no cover - unexpected runtime issue
            logger.error("PaddleOCR inference failed on %s: %s", platform.system(), exc)
            import traceback

            logger.error("Full traceback: %s", traceback.format_exc())
            return []

        # Complete timing measurements
        if timing and overall_start_time:
            timing.total_time = time.perf_counter() - overall_start_time
            self._last_timing_results = timing
            # Log timing summary for Windows/WSL comparison (Issue #170)
            platform_info = f"{platform.system()}/{platform.machine()}"
            timing.log_summary(platform_info)

        return self._parse_ocr_results(raw_results)

    def _run_ocr_with_timing(
        self, image: np.ndarray, timing: Optional[OCRStageTimings], timeout_seconds: int = 30
    ) -> Any:
        """Execute OCR with detailed stage timing for Issue #170."""
        if timing is None:
            # Fallback to normal execution without timing
            return self._run_ocr_with_timeout(image, timeout_seconds)

        # Attempt to measure actual stage timings through PaddleX pipeline access
        try:
            return self._run_ocr_with_actual_timing(image, timing, timeout_seconds)
        except Exception as e:
            logger.warning("Failed to measure actual OCR stage timings: %s", e)
            # Fallback to total time measurement only
            return self._run_ocr_with_total_timing_only(image, timing, timeout_seconds)

    def _run_ocr_with_actual_timing(
        self, image: np.ndarray, timing: OCRStageTimings, timeout_seconds: int = 30
    ) -> Any:
        """Execute OCR with actual stage-by-stage timing measurements.

        Preserves timeout functionality for platforms where PaddleOCR can stall.
        """
        # Check if we need special timeout handling (Apple Silicon)
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            # Use process-based timing for Apple Silicon with timeout protection
            return self._run_ocr_stage_timing_in_process(image, timing, timeout_seconds)

        # For other platforms, run stage timing directly
        return self._run_ocr_stage_timing_direct(image, timing)

    def _run_ocr_stage_timing_direct(self, image: np.ndarray, timing: OCRStageTimings) -> Any:
        """Execute stage timing directly (non-Apple Silicon platforms)."""
        # Access PaddleX pipeline for individual model timing
        pipeline = self._ocr._create_paddlex_pipeline()

        if not hasattr(pipeline, "text_det_model") or not hasattr(pipeline, "text_rec_model"):
            raise RuntimeError("PaddleX pipeline does not expose individual models")

        # Stage 1: Text Detection
        det_start_time = time.perf_counter()
        try:
            det_results = pipeline.text_det_model.predict([image])
            # Handle generator result if needed
            if hasattr(det_results, "__iter__") and not isinstance(det_results, (list, tuple)):
                det_results = list(det_results)
        except Exception as e:
            raise RuntimeError(f"Text detection failed: {e}")
        timing.detection_time = time.perf_counter() - det_start_time

        # Check if detection found any text regions
        if not det_results or len(det_results) == 0:
            # No text detected, set remaining stages to zero
            timing.classification_time = 0.0
            timing.recognition_time = 0.0
            return [[]]  # Return empty result in expected format

        # Handle the case where det_results is a generator or has different structure
        first_result = det_results[0] if isinstance(det_results, (list, tuple)) else det_results
        if not hasattr(first_result, "get") or not first_result.get("dt_polys"):
            # No text regions found, skip remaining stages
            timing.classification_time = 0.0
            timing.recognition_time = 0.0
            return [[]]

        # Stage 2: Text Line Orientation (Classification) - if enabled
        cls_start_time = time.perf_counter()
        if hasattr(pipeline, "text_cls_model") and pipeline.text_cls_model is not None:
            try:
                # Extract text regions for classification
                text_regions = first_result["dt_polys"]
                # Run classification on detected regions
                cls_results = pipeline.text_cls_model.predict(text_regions)
                if hasattr(cls_results, "__iter__") and not isinstance(cls_results, (list, tuple)):
                    cls_results = list(cls_results)
            except Exception as e:
                logger.warning("Text classification failed: %s", e)
                # Continue without classification
        timing.classification_time = time.perf_counter() - cls_start_time

        # Stage 3: Text Recognition
        rec_start_time = time.perf_counter()
        try:
            rec_results = pipeline.text_rec_model.predict(det_results)
            # Handle generator result if needed
            if hasattr(rec_results, "__iter__") and not isinstance(rec_results, (list, tuple)):
                rec_results = list(rec_results)
        except Exception as e:
            raise RuntimeError(f"Text recognition failed: {e}")
        timing.recognition_time = time.perf_counter() - rec_start_time

        # Combine results in expected format
        final_results = self._combine_detection_recognition_results(det_results, rec_results)
        return [final_results]

    def _run_ocr_stage_timing_in_process(
        self, image: np.ndarray, timing: OCRStageTimings, timeout_seconds: int = 30
    ) -> Any:
        """Execute stage timing in a separate process for Apple Silicon with timeout protection."""
        logger.info("Using process-based stage timing for Apple Silicon timeout protection")

        # For Apple Silicon, fall back to total timing only to preserve timeout functionality
        # This ensures we don't reintroduce the freeze issue while still providing timing data
        return self._run_ocr_with_total_timing_only(image, timing, timeout_seconds)

    def _run_ocr_with_total_timing_only(
        self, image: np.ndarray, timing: OCRStageTimings, timeout_seconds: int = 30
    ) -> Any:
        """Fallback: measure only total OCR time without stage breakdown."""
        logger.info("Using fallback timing measurement (total time only)")

        ocr_start_time = time.perf_counter()
        raw_results = self._run_ocr_with_timeout(image, timeout_seconds)
        total_ocr_time = time.perf_counter() - ocr_start_time

        # Set individual stage times to zero to indicate they were not measured
        timing.detection_time = 0.0
        timing.classification_time = 0.0
        timing.recognition_time = total_ocr_time  # Put all time in recognition as fallback

        return raw_results

    def _combine_detection_recognition_results(
        self, det_results: Any, rec_results: Any
    ) -> List[Any]:
        """Combine detection and recognition results into the expected OCR format."""
        combined: list[Any] = []
        if not det_results or not rec_results:
            return combined

        # This is a simplified combination - the actual implementation
        # would depend on the specific format returned by PaddleX models
        try:
            polys = det_results[0].get("dt_polys", [])
            texts = rec_results[0].get("rec_texts", []) if rec_results else []
            scores = rec_results[0].get("rec_scores", []) if rec_results else []

            for i, poly in enumerate(polys):
                text = texts[i] if i < len(texts) else ""
                score = scores[i] if i < len(scores) else 0.0
                combined.append([poly, (text, score)])

        except (IndexError, KeyError, TypeError) as e:
            logger.warning("Failed to combine detection/recognition results: %s", e)
            return []

        return combined

    def _run_ocr_with_timeout(self, image: np.ndarray, timeout_seconds: int = 30) -> Any:
        """Apple Siliconでのフリーズ対策: プロセスベースのタイムアウト付きOCR実行"""
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            # Apple Silicon以外では通常の実行
            return self._ocr.ocr(image)

        # Apple Siliconの場合はプロセスベースでタイムアウト付き実行
        # プロセスはタイムアウト時に強制終了可能でスレッドリークを防ぐ
        try:
            return self._run_ocr_in_process(image, timeout_seconds)
        except TimeoutError:
            # タイムアウトエラーは伝播させてフォールバックでの再フリーズを防ぐ
            logger.error(
                "Process-based OCR timed out on Apple Silicon, aborting to prevent re-freeze"
            )
            raise
        except Exception as e:
            logger.error("Process-based OCR failed on Apple Silicon: %s", e)
            # プロセス作成などの技術的な失敗の場合のみフォールバック
            # ただし、直接実行も同様にフリーズする可能性があるため空の結果を返す
            logger.warning(
                "Process creation failed, returning empty OCR result to avoid potential freeze"
            )
            return []

    def _run_ocr_in_process(self, image: np.ndarray, timeout_seconds: int) -> Any:
        """プロセスベースでOCRを実行（Apple Silicon専用）"""
        # プロセス間でPaddleOCRエンジンを共有できないため、
        # 設定情報を渡して子プロセス内でエンジンを再初期化
        engine_config = {
            "models_root": str(self.models_root) if self.models_root else None,
            "language": self.language,
            "confidence_threshold": self.confidence_threshold,
            "max_image_pixels": self.max_image_pixels,
            "max_side_length": self.max_side_length,
        }

        # マルチプロセシング用のキューで結果を受け取る
        result_queue: multiprocessing.Queue[Any] = multiprocessing.Queue()

        # 子プロセスでOCR実行
        process = multiprocessing.Process(
            target=_ocr_worker_process,
            args=(engine_config, image, result_queue),
            daemon=True,
        )

        process.start()
        process.join(timeout=timeout_seconds)

        if process.is_alive():
            logger.error(
                "OCR process timed out on Apple Silicon after %d seconds",
                timeout_seconds,
            )
            # プロセスを強制終了（スレッドと違い確実に終了可能）
            process.terminate()
            process.join(timeout=5)  # 終了を待機
            if process.is_alive():
                logger.warning("Force killing OCR process")
                process.kill()
                process.join()

            # プロセス終了後はエンジンを無効化して次回再初期化
            self._ocr = None
            raise TimeoutError(
                f"OCR process timed out after {timeout_seconds} seconds on Apple Silicon"
            )

        # プロセスが正常終了した場合は結果を取得
        # Queue.empty()は信頼性がないため、get_nowait()でレースコンディションを回避
        try:
            result_data = result_queue.get_nowait()
            if isinstance(result_data, dict) and "error" in result_data:
                raise Exception(result_data["error"])
            return result_data
        except queue.Empty:
            # キューが空の場合
            # プロセス終了後も結果転送が完了していない可能性があるため短時間待機して再試行
            try:
                result_data = result_queue.get(timeout=2.0)
                if isinstance(result_data, dict) and "error" in result_data:
                    raise Exception(result_data["error"])
                return result_data
            except queue.Empty:
                raise RuntimeError("OCR process completed but no result was returned")
        except Exception as e:
            # その他のエラー（result_dataの処理エラーなど）
            raise e

    # ------------------------------------------------------------------
    def _parse_ocr_results(self, results: Any) -> List[OCRResult]:
        parsed: List[OCRResult] = []
        if not results:
            return parsed

        first_item = results[0]
        if first_item is None:
            return parsed

        if isinstance(first_item, Mapping):
            rec_texts = first_item.get("rec_texts", [])
            rec_scores = first_item.get("rec_scores", [])
            rec_polys = first_item.get("rec_polys", [])
            for text, score, poly in zip(rec_texts, rec_scores, rec_polys):
                if score is None or float(score) < self.confidence_threshold:
                    continue
                if not isinstance(text, str) or not text.strip():
                    continue
                bbox = self._polygon_to_bbox(poly)
                parsed.append(OCRResult(text=text.strip(), confidence=float(score), bbox=bbox))
            return parsed

        # Legacy list format [[box, (text, score)], ...]
        try:
            for item in first_item:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                box, text_conf = item
                result_text: str
                result_score: float
                if isinstance(text_conf, (list, tuple)) and len(text_conf) == 2:
                    result_text = str(text_conf[0])
                    result_score = float(text_conf[1])
                else:
                    result_text = str(text_conf)
                    result_score = 1.0

                if result_score < self.confidence_threshold or not result_text.strip():
                    continue

                bbox = self._polygon_to_bbox(box)
                parsed.append(
                    OCRResult(text=result_text.strip(), confidence=result_score, bbox=bbox)
                )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to parse OCR result item: %s", exc)

        return parsed

    @staticmethod
    def _polygon_to_bbox(polygon: Any) -> Tuple[int, int, int, int]:
        try:
            xs = [int(point[0]) for point in polygon]
            ys = [int(point[1]) for point in polygon]
            x = min(xs)
            y = min(ys)
            w = max(xs) - x
            h = max(ys) - y
            return x, y, w, h
        except Exception:  # pragma: no cover - fallback for malformed data
            return 0, 0, 0, 0


# ---------------------------------------------------------------------------
# Process worker function for Apple Silicon OCR -------------------------------
# ---------------------------------------------------------------------------


def _ocr_worker_process(
    engine_config: Dict[str, Any],
    image: np.ndarray,
    result_queue: multiprocessing.Queue,
) -> None:
    """子プロセスでOCRを実行（Apple Silicon用）"""
    try:
        # 子プロセス内でPaddleOCRエンジンを初期化
        if not PADDLEOCR_AVAILABLE:
            result_queue.put({"error": "PaddleOCR not available in worker process"})
            return

        # Apple Silicon最適化の環境変数を設定
        os.environ.setdefault("VECLIB_MAXIMUM_THREADS", str(min(8, os.cpu_count() or 4)))
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")
        os.environ.setdefault("PADDLE_CPU_ONLY", "1")
        os.environ.setdefault("BLAS", "Accelerate")
        os.environ.setdefault("FLAGS_use_mkldnn", "false")
        os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
        os.environ.setdefault("FLAGS_call_stack_level", "2")

        # 一時的なエンジンインスタンスを作成
        temp_engine = SimplePaddleOCREngine(
            language=engine_config["language"],
            confidence_threshold=engine_config["confidence_threshold"],
            models_root=(
                Path(engine_config["models_root"]) if engine_config["models_root"] else None
            ),
            max_image_pixels=engine_config["max_image_pixels"],
            max_side_length=engine_config["max_side_length"],
        )

        # エンジンを初期化
        if not temp_engine.initialize():
            result_queue.put({"error": "Failed to initialize PaddleOCR in worker process"})
            return

        # OCR実行
        ocr_result = temp_engine._ocr.ocr(image)
        result_queue.put(ocr_result)

    except Exception as e:
        result_queue.put({"error": str(e)})


__all__ = [
    "OCRResult",
    "OCRStageTimings",
    "SimplePaddleOCREngine",
    "PADDLEOCR_AVAILABLE",
    "PADDLEX_AVAILABLE",
    "_create_safe_paddleocr_kwargs",
    "OCRModelDownloader",
]
