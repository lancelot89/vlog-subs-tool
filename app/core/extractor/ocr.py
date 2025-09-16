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
        elif key in {"show_log", "use_space_char"}:
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

        if platform.system() == "Windows":  # pragma: no cover - platform specific
            os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
            os.environ.setdefault("OMP_NUM_THREADS", "1")
            os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
            os.environ.setdefault("PADDLE_CPU_ONLY", "1")
            os.environ.setdefault("PYTHONPATH", "")
            logger.debug("Applied Windows specific PaddleOCR environment tweaks")

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

            config_candidates = [
                # Newer PaddleOCR (v3.x) parameter names
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
                },
                # Minimal parameters (last resort)
                {
                    "det_model_dir": str(det_dir.resolve()),
                    "rec_model_dir": str(rec_dir.resolve()),
                    "lang": lang,
                },
            ]

            errors: List[str] = []
            for config in config_candidates:
                kwargs = _create_safe_paddleocr_kwargs(config)
                try:
                    logger.debug("Initialising PaddleOCR on %s with kwargs=%s", platform.system(), kwargs)
                    self._ocr = PaddleOCR(**kwargs)  # type: ignore[misc]
                    if self._ocr is None:
                        raise RuntimeError("PaddleOCR returned None instance")
                    logger.info(
                        "PaddleOCR initialised successfully on %s using configuration keys: %s",
                        platform.system(),
                        ", ".join(sorted(kwargs.keys())),
                    )
                    return True
                except Exception as exc:  # pragma: no cover - exercised via tests
                    error_msg = f"{type(exc).__name__}: {exc}"
                    errors.append(error_msg)
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

        # Ensure uint8 BGR format expected by PaddleOCR
        processed = image
        if processed.dtype != np.uint8:
            processed = np.clip(processed, 0, 255).astype(np.uint8)

        if processed.ndim == 2:
            processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
        elif processed.ndim == 3 and processed.shape[2] == 4:
            processed = cv2.cvtColor(processed, cv2.COLOR_BGRA2BGR)
        elif processed.ndim != 3:
            return None

        if not processed.flags.get("C_CONTIGUOUS", False):
            processed = np.ascontiguousarray(processed)

        height, width = processed.shape[:2]
        if height <= 0 or width <= 0:
            return None

        total_pixels = height * width
        if self.max_image_pixels > 0 and total_pixels > self.max_image_pixels:
            scale = (self.max_image_pixels / float(total_pixels)) ** 0.5
            new_w = max(1, int(width * scale))
            new_h = max(1, int(height * scale))
            processed = cv2.resize(processed, (new_w, new_h), interpolation=cv2.INTER_AREA)
            height, width = processed.shape[:2]

        if self.max_side_length > 0 and (height > self.max_side_length or width > self.max_side_length):
            scale = min(self.max_side_length / float(height), self.max_side_length / float(width))
            new_w = max(1, int(width * scale))
            new_h = max(1, int(height * scale))
            processed = cv2.resize(processed, (new_w, new_h), interpolation=cv2.INTER_AREA)

        return processed

    def _extract_from_single(self, image: Optional[np.ndarray]) -> List[OCRResult]:
        if image is None:
            return []

        processed = self._preprocess_image(image)
        if processed is None:
            return []

        try:
            raw_results = self._ocr.ocr(processed)  # type: ignore[operator]
        except (MemoryError, RuntimeError, ValueError) as exc:
            logger.error("PaddleOCR memory/runtime error on %s: %s", platform.system(), exc)
            return []
        except Exception as exc:  # pragma: no cover - unexpected runtime issue
            logger.error("PaddleOCR inference failed on %s: %s", platform.system(), exc)
            return []

        return self._parse_ocr_results(raw_results)

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


__all__ = [
    "OCRResult",
    "SimplePaddleOCREngine",
    "PADDLEOCR_AVAILABLE",
    "PADDLEX_AVAILABLE",
    "_create_safe_paddleocr_kwargs",
    "OCRModelDownloader",
]
