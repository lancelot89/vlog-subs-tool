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

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple, Union
import logging
import os
import platform
import sys

import cv2  # type: ignore
import numpy as np
import signal
import threading
import time
import multiprocessing
import pickle
import queue
import subprocess
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flags --------------------------------------------------------
# ---------------------------------------------------------------------------
try:  # pragma: no cover - availability detection
    from paddleocr import PaddleOCR  # type: ignore

    PADDLEOCR_AVAILABLE = True
    _PADDLE_IMPORT_ERROR: Optional[Exception] = None
except Exception as _import_error:  # pragma: no cover - dependency missing
    PaddleOCR = None  # type: ignore
    PADDLEOCR_AVAILABLE = False
    _PADDLE_IMPORT_ERROR = _import_error

try:  # pragma: no cover - optional dependency detection
    import paddlex  # type: ignore

    PADDLEX_AVAILABLE = True
except Exception:  # pragma: no cover - paddlex is optional
    PADDLEX_AVAILABLE = False

# ---------------------------------------------------------------------------
# Windows Performance Optimization Helpers ---------------------------------
# ---------------------------------------------------------------------------

def _get_cpu_info():
    """Get CPU information for Windows optimization."""
    try:
        if platform.system() == "Windows":
            # Use wmic to get CPU information
            result = subprocess.run(
                ["wmic", "cpu", "get", "Name,NumberOfCores,NumberOfLogicalProcessors", "/format:csv"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                for line in lines[1:]:  # Skip header
                    parts = line.split(',')
                    if len(parts) >= 3:
                        name = parts[1] if len(parts) > 1 else ""
                        cores = parts[2] if len(parts) > 2 else "0"
                        logical = parts[3] if len(parts) > 3 else "0"
                        return {
                            "name": name,
                            "cores": int(cores) if cores.isdigit() else 0,
                            "logical_processors": int(logical) if logical.isdigit() else 0
                        }
        else:
            # For non-Windows, use /proc/cpuinfo
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    content = f.read()
                    name_match = re.search(r'model name\s*:\s*(.+)', content)
                    name = name_match.group(1).strip() if name_match else "Unknown"
                    cores = content.count('processor\t:')
                    return {
                        "name": name,
                        "cores": cores,
                        "logical_processors": cores
                    }
            except Exception:
                pass
    except Exception as e:
        logger.debug("Failed to get CPU info: %s", e)

    # Fallback
    return {
        "name": "Unknown",
        "cores": os.cpu_count() or 4,
        "logical_processors": os.cpu_count() or 4
    }

def _get_cpu_generation(cpu_name):
    """Extract Intel CPU generation from name."""
    if "Intel" in cpu_name:
        # Look for patterns like "i7-10700K" or "i5-11400"
        match = re.search(r'i[3579]-(\d{1,2})\d{3}', cpu_name)
        if match:
            gen_str = match.group(1)
            # Handle single digit (8th gen) vs double digit (10th gen+)
            if len(gen_str) == 1:
                return int(gen_str)
            else:
                return int(gen_str)
        # Look for newer naming like "12th Gen"
        match = re.search(r'(\d+)th Gen', cpu_name)
        if match:
            return int(match.group(1))
    return 8  # Conservative default

def _get_optimal_windows_threads(cpu_info):
    """Calculate optimal thread count for Windows OCR performance."""
    cpu_count = cpu_info.get("logical_processors", os.cpu_count() or 4)
    cpu_name = cpu_info.get("name", "")
    cpu_generation = _get_cpu_generation(cpu_name)

    logger.debug("CPU: %s, Generation: %d, Logical CPUs: %d", cpu_name, cpu_generation, cpu_count)

    # Intel 10th generation and newer can handle more aggressive threading
    if cpu_generation >= 10 and "Intel" in cpu_name:
        optimal = min(6, max(2, cpu_count))
    # AMD Ryzen processors generally handle threading well
    elif "AMD" in cpu_name and ("Ryzen" in cpu_name or "EPYC" in cpu_name):
        optimal = min(6, max(2, cpu_count))
    # Conservative setting for older Intel CPUs (but still better than single thread)
    elif "Intel" in cpu_name:
        optimal = min(4, max(2, cpu_count // 2))
    # Very conservative for unknown CPUs
    else:
        optimal = min(3, max(2, cpu_count // 4))

    logger.debug("Calculated optimal thread count: %d", optimal)
    return optimal

# ---------------------------------------------------------------------------
# Helper data structures ----------------------------------------------------
# ---------------------------------------------------------------------------


@dataclass
class OCRResult:
    """Container for a single OCR detection."""

    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, w, h


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
        elif key in {"show_log", "use_space_char", "use_gpu"}:
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

        # Apple Silicon specific optimizations
        if platform.system() == "Darwin" and platform.machine() == "arm64":  # pragma: no cover - platform specific
            # Optimize for Apple Silicon M1/M2/M3 processors
            os.environ.setdefault("VECLIB_MAXIMUM_THREADS", str(min(8, os.cpu_count() or 4)))
            os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # Disable OpenBLAS to avoid conflicts
            os.environ.setdefault("MKL_NUM_THREADS", "1")
            os.environ.setdefault("PADDLE_CPU_ONLY", "1")
            os.environ.setdefault("BLAS", "Accelerate")  # Prefer Apple Accelerate framework
            os.environ.setdefault("FLAGS_use_mkldnn", "false")  # Disable MKLDNN on Apple Silicon
            os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")
            logger.debug("Applied Apple Silicon specific PaddleOCR environment tweaks")

        if platform.system() == "Windows":  # pragma: no cover - platform specific
            # Get CPU information for optimal thread configuration
            cpu_info = _get_cpu_info()
            optimal_threads = _get_optimal_windows_threads(cpu_info)

            # Apply optimized threading configuration
            os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
            os.environ.setdefault("OMP_NUM_THREADS", str(optimal_threads))
            os.environ.setdefault("OPENBLAS_NUM_THREADS", str(optimal_threads))
            os.environ.setdefault("PADDLE_CPU_ONLY", "1")
            os.environ.setdefault("PYTHONPATH", "")

            # Intel specific optimizations
            if "Intel" in cpu_info.get("name", ""):
                os.environ.setdefault("MKL_NUM_THREADS", str(optimal_threads))
                os.environ.setdefault("INTEL_NUM_THREADS", str(optimal_threads))

            # AMD specific optimizations
            elif "AMD" in cpu_info.get("name", ""):
                os.environ.setdefault("OPENBLAS_CORETYPE", "RYZEN")

            # Windows環境でのvector<bool> subscriptエラー回避
            os.environ.setdefault("PADDLE_SKIP_GPU_MEMORY_INIT", "1")
            os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")

            logger.info("Applied Windows performance optimizations: %d threads for %s",
                       optimal_threads, cpu_info.get("name", "Unknown CPU"))

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

            # Windows環境でのvector<bool> subscriptエラー回避のための設定
            is_windows = platform.system() == "Windows"

            if is_windows:
                # Windows環境では段階的に性能向上設定を試行
                cpu_info = _get_cpu_info()
                cpu_generation = _get_cpu_generation(cpu_info.get("name", ""))

                config_candidates = [
                    # Phase 1: 積極的性能最適化 (新しいCPU向け)
                    {
                        "text_detection_model_dir": str(det_dir.resolve()),
                        "text_recognition_model_dir": str(rec_dir.resolve()),
                        "lang": lang,
                        "use_textline_orientation": True,  # 角度検出有効化
                        "use_gpu": False,
                        "use_space_char": True,
                        "drop_score": 0.5,
                        "enable_mkldnn": True,  # MKL-DNN有効化
                        "max_text_length": 25,
                    } if cpu_generation >= 10 else None,
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
                        "max_text_length": 25,
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
                        "max_text_length": 25,
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
                        phase_names = ["Aggressive Performance", "Moderate Optimization", "Safe Configuration", "Legacy Fallback"]
                        phase_name = phase_names[min(i, len(phase_names) - 1)]
                        logger.info("Trying Windows %s configuration...", phase_name)

                    logger.debug("Initialising PaddleOCR on %s with kwargs=%s", platform.system(), kwargs)
                    self._ocr = PaddleOCR(**kwargs)  # type: ignore[misc]
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
                        logger.warning("PaddleOCR initialisation failed (%s): %s", platform.system(), exc)
                    self._ocr = None
                    continue

            logger.error("All PaddleOCR configurations failed on %s: %s", platform.system(), "; ".join(errors))
            return False

        except FileNotFoundError as exc:
            logger.error("PaddleOCR model files not found on %s: %s", platform.system(), exc)
            self._ocr = None
            return False
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("PaddleOCR initialisation failed on %s: %s", platform.system(), exc)
            self._ocr = None
            return False

    # ----------------------- inference helpers -----------------------
    def extract_text(self, image_input: Union[np.ndarray, Mapping[str, Any], Sequence[Any], Any]) -> List[OCRResult]:
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
                value = image_like.get(key)  # type: ignore[index]
                if isinstance(value, np.ndarray):
                    return value
        return None

    def _preprocess_image(self, image: np.ndarray) -> Optional[np.ndarray]:
        if image is None or image.size == 0:
            return None

        if not isinstance(image, np.ndarray):
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
            if self.max_side_length > 0 and (height > self.max_side_length or width > self.max_side_length):
                scale = min(self.max_side_length / float(height), self.max_side_length / float(width))
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
                logger.warning(f"Final processed image has invalid size: {final_width}x{final_height}")
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

        processed = self._preprocess_image(image)
        if processed is None:
            return []

        # OCR実行前の最終検証
        try:
            if not isinstance(processed, np.ndarray):
                logger.warning("Processed image is not a numpy array")
                return []

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

            logger.debug(f"Sending image to OCR: shape={processed.shape}, dtype={processed.dtype}, contiguous={processed.flags.c_contiguous}")

            # PaddleOCRの実行（Apple Siliconでのフリーズ対策でタイムアウト付き）
            raw_results = self._run_ocr_with_timeout(processed, timeout_seconds=30)

        except IndexError as exc:
            # Windows環境でのvector<bool> subscriptエラーの特別処理
            if "vector" in str(exc) and "subscript" in str(exc):
                logger.warning("Windows-specific PaddleX vector error detected, skipping image: %s", exc)
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

        return self._parse_ocr_results(raw_results)

    def _run_ocr_with_timeout(self, image: np.ndarray, timeout_seconds: int = 30) -> Any:
        """Apple Siliconでのフリーズ対策: プロセスベースのタイムアウト付きOCR実行"""
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            # Apple Silicon以外では通常の実行
            return self._ocr.ocr(image)  # type: ignore[operator]

        # Apple Siliconの場合はプロセスベースでタイムアウト付き実行
        # プロセスはタイムアウト時に強制終了可能でスレッドリークを防ぐ
        try:
            return self._run_ocr_in_process(image, timeout_seconds)
        except TimeoutError:
            # タイムアウトエラーは伝播させてフォールバックでの再フリーズを防ぐ
            logger.error("Process-based OCR timed out on Apple Silicon, aborting to prevent re-freeze")
            raise
        except Exception as e:
            logger.error("Process-based OCR failed on Apple Silicon: %s", e)
            # プロセス作成などの技術的な失敗の場合のみフォールバック
            # ただし、直接実行も同様にフリーズする可能性があるため空の結果を返す
            logger.warning("Process creation failed, returning empty OCR result to avoid potential freeze")
            return []

    def _run_ocr_in_process(self, image: np.ndarray, timeout_seconds: int) -> Any:
        """プロセスベースでOCRを実行（Apple Silicon専用）"""
        # プロセス間でPaddleOCRエンジンを共有できないため、
        # 設定情報を渡して子プロセス内でエンジンを再初期化
        engine_config = {
            'models_root': str(self.models_root) if self.models_root else None,
            'language': self.language,
            'confidence_threshold': self.confidence_threshold,
            'max_image_pixels': self.max_image_pixels,
            'max_side_length': self.max_side_length,
        }

        # マルチプロセシング用のキューで結果を受け取る
        result_queue = multiprocessing.Queue()

        # 子プロセスでOCR実行
        process = multiprocessing.Process(
            target=_ocr_worker_process,
            args=(engine_config, image, result_queue),
            daemon=True
        )

        process.start()
        process.join(timeout=timeout_seconds)

        if process.is_alive():
            logger.error("OCR process timed out on Apple Silicon after %d seconds", timeout_seconds)
            # プロセスを強制終了（スレッドと違い確実に終了可能）
            process.terminate()
            process.join(timeout=5)  # 終了を待機
            if process.is_alive():
                logger.warning("Force killing OCR process")
                process.kill()
                process.join()

            # プロセス終了後はエンジンを無効化して次回再初期化
            self._ocr = None
            raise TimeoutError(f"OCR process timed out after {timeout_seconds} seconds on Apple Silicon")

        # プロセスが正常終了した場合は結果を取得
        # Queue.empty()は信頼性がないため、get_nowait()でレースコンディションを回避
        try:
            result_data = result_queue.get_nowait()
            if isinstance(result_data, dict) and 'error' in result_data:
                raise Exception(result_data['error'])
            return result_data
        except queue.Empty:
            # キューが空の場合
            # プロセス終了後も結果転送が完了していない可能性があるため短時間待機して再試行
            try:
                result_data = result_queue.get(timeout=2.0)
                if isinstance(result_data, dict) and 'error' in result_data:
                    raise Exception(result_data['error'])
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
                text: str
                score: float
                if isinstance(text_conf, (list, tuple)) and len(text_conf) == 2:
                    text = str(text_conf[0])
                    score = float(text_conf[1])
                else:
                    text = str(text_conf)
                    score = 1.0

                if score < self.confidence_threshold or not text.strip():
                    continue

                bbox = self._polygon_to_bbox(box)
                parsed.append(OCRResult(text=text.strip(), confidence=score, bbox=bbox))
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

def _ocr_worker_process(engine_config: Dict[str, Any], image: np.ndarray, result_queue: multiprocessing.Queue) -> None:
    """子プロセスでOCRを実行（Apple Silicon用）"""
    try:
        # 子プロセス内でPaddleOCRエンジンを初期化
        if not PADDLEOCR_AVAILABLE:
            result_queue.put({'error': 'PaddleOCR not available in worker process'})
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
            language=engine_config['language'],
            confidence_threshold=engine_config['confidence_threshold'],
            models_root=Path(engine_config['models_root']) if engine_config['models_root'] else None,
            max_image_pixels=engine_config['max_image_pixels'],
            max_side_length=engine_config['max_side_length'],
        )

        # エンジンを初期化
        if not temp_engine.initialize():
            result_queue.put({'error': 'Failed to initialize PaddleOCR in worker process'})
            return

        # OCR実行
        ocr_result = temp_engine._ocr.ocr(image)  # type: ignore[operator]
        result_queue.put(ocr_result)

    except Exception as e:
        result_queue.put({'error': str(e)})


__all__ = [
    "OCRResult",
    "SimplePaddleOCREngine",
    "PADDLEOCR_AVAILABLE",
    "PADDLEX_AVAILABLE",
    "_create_safe_paddleocr_kwargs",
    "OCRModelDownloader",
]
