"""
Minimal PaddleOCR wrapper for this app.
- Uses bundled models under app/models/paddleocr (PP-OCRv5_server_det/rec).
- CPU-only, no PaddleX, no network download, no Tesseract.
- Clean API: initialize() -> bool, extract_text(np.ndarray) -> List[OCRResult].
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional
import logging
import os
import sys
import platform
import numpy as np
import cv2

try:
    from paddleocr import PaddleOCR  # type: ignore
except Exception as e:  # ImportError and others
    raise ImportError(
        "PaddleOCR is required. Install with: pip install paddlepaddle paddleocr\n"
        f"Import error: {e}"
    )

@dataclass
class OCRResult:
    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, w, h


class SimplePaddleOCREngine:
    """
    Very small wrapper around PaddleOCR that only uses bundled models.

    Directory layout expected:
      app/models/paddleocr/
        ├─ PP-OCRv5_server_det/   (det model files)
        └─ PP-OCRv5_server_rec/   (rec model files)
    """

    def __init__(self, language: str = "ja", confidence_threshold: float = 0.7,
                 models_root: Optional[Path] = None) -> None:
        self.language = language
        self.confidence_threshold = confidence_threshold
        self.models_root = models_root  # if None, auto-discover under app/models/paddleocr
        self._ocr = None

    # ---------- path resolution ----------
    def _resolve_models_root(self) -> Path:
        """
        Resolve the app's bundled paddleocr models directory.
        Cross-platform compatible path resolution.
        Search precedence:
          1) explicit models_root if provided
          2) env PADDLE_MODELS_DIR (absolute/relative allowed)
          3) ascend up to 6 parents from this file to find 'app/models/paddleocr'
          4) cwd/app/models/paddleocr
        """
        # 1) explicit arg
        if self.models_root and (self.models_root / "PP-OCRv5_server_det").exists():
            logging.debug(f"Using explicit models_root: {self.models_root}")
            return self.models_root

        # 2) env var
        env_dir = os.environ.get("PADDLE_MODELS_DIR")
        if env_dir:
            try:
                p = Path(env_dir).resolve()
                if (p / "PP-OCRv5_server_det").exists():
                    logging.debug(f"Using env PADDLE_MODELS_DIR: {p}")
                    return p
            except Exception as e:
                logging.warning(f"Invalid PADDLE_MODELS_DIR path '{env_dir}': {e}")

        # 3) ascend parents - with cross-platform path handling
        here = Path(__file__).resolve()
        for parent in [here.parent] + list(here.parents)[:6]:
            candidate = parent / "app" / "models" / "paddleocr"
            if (candidate / "PP-OCRv5_server_det").exists() and (candidate / "PP-OCRv5_server_rec").exists():
                logging.debug(f"Found models in parent directory: {candidate}")
                return candidate

        # 4) cwd fallback
        candidate = Path.cwd() / "app" / "models" / "paddleocr"
        if (candidate / "PP-OCRv5_server_det").exists() and (candidate / "PP-OCRv5_server_rec").exists():
            logging.debug(f"Using cwd models directory: {candidate}")
            return candidate

        # 5) Additional Windows-specific search paths
        if platform.system() == "Windows":
            # Check for frozen application paths
            if getattr(sys, 'frozen', False):
                frozen_dir = Path(sys.executable).parent / "app" / "models" / "paddleocr"
                if (frozen_dir / "PP-OCRv5_server_det").exists() and (frozen_dir / "PP-OCRv5_server_rec").exists():
                    logging.debug(f"Found models in frozen app directory: {frozen_dir}")
                    return frozen_dir

            # Check AppData or user directories
            if 'APPDATA' in os.environ:
                appdata_dir = Path(os.environ['APPDATA']) / "vlog-subs-tool" / "models" / "paddleocr"
                if (appdata_dir / "PP-OCRv5_server_det").exists() and (appdata_dir / "PP-OCRv5_server_rec").exists():
                    logging.debug(f"Found models in AppData: {appdata_dir}")
                    return appdata_dir

        raise FileNotFoundError(
            f"Bundled PaddleOCR models not found on {platform.system()}. Expected at app/models/paddleocr/"
            " with PP-OCRv5_server_det and PP-OCRv5_server_rec subdirs."
            f" Searched paths: {here.parents[0]}/app/models/paddleocr, {Path.cwd()}/app/models/paddleocr"
        )

    # ---------- init ----------
    def initialize(self) -> bool:
        """
        Initialize PaddleOCR with bundled models. CPU-only.
        Cross-platform compatibility ensured for Windows/Linux/macOS.
        """
        try:
            # Cross-platform CPU-only setup
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
            os.environ.setdefault("FLAGS_call_stack_level", "2")

            # Windows-specific environment variables for stability
            if platform.system() == "Windows":
                os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
                os.environ.setdefault("OMP_NUM_THREADS", "1")
                os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
                logging.debug("Applied Windows-specific PaddleOCR environment settings")

            root = self._resolve_models_root()
            det_dir = root / "PP-OCRv5_server_det"
            rec_dir = root / "PP-OCRv5_server_rec"

            # Ensure paths exist on all platforms
            if not det_dir.exists() or not rec_dir.exists():
                raise FileNotFoundError(f"Model directories not found: {det_dir}, {rec_dir}")

            lang = "japan" if self.language.lower() in {"ja", "jpn", "japanese"} else self.language

            # Try multiple parameter configurations for cross-platform compatibility
            success = False
            error_messages = []

            # Configuration 1: Latest PaddleOCR parameters (preferred)
            kwargs_latest = {
                "text_detection_model_dir": str(det_dir.resolve()),
                "text_recognition_model_dir": str(rec_dir.resolve()),
                "lang": lang,
                "use_textline_orientation": True,
                "text_det_limit_side_len": 1536,  # Limit detection resolution
                "text_det_limit_type": "max",  # Max dimension limit
            }

            # Configuration 2: Legacy parameters (fallback for older PaddleOCR versions)
            kwargs_legacy = {
                "det_model_dir": str(det_dir.resolve()),
                "rec_model_dir": str(rec_dir.resolve()),
                "lang": lang,
                "use_angle_cls": True,
            }

            # Configuration 3: Minimal parameters (last resort)
            kwargs_minimal = {
                "det_model_dir": str(det_dir.resolve()),
                "rec_model_dir": str(rec_dir.resolve()),
                "lang": lang,
            }

            for config_name, kwargs in [
                ("latest", kwargs_latest),
                ("legacy", kwargs_legacy),
                ("minimal", kwargs_minimal)
            ]:
                try:
                    logging.debug(f"Platform: {platform.system()}")
                    logging.debug(f"Trying {config_name} PaddleOCR config: {kwargs}")
                    self._ocr = PaddleOCR(**kwargs)
                    logging.info(f"PaddleOCR initialized successfully on {platform.system()} using {config_name} config.")
                    success = True
                    break
                except Exception as e:
                    error_msg = f"{config_name} config failed: {e}"
                    error_messages.append(error_msg)
                    logging.warning(error_msg)
                    continue

            if not success:
                combined_errors = "; ".join(error_messages)
                raise Exception(f"All PaddleOCR configurations failed: {combined_errors}")
            return True
        except Exception as e:
            logging.error(f"PaddleOCR initialization failed on {platform.system()}: {e}")
            self._ocr = None
            return False

    # ---------- inference ----------
    def extract_text(self, image: np.ndarray) -> List[OCRResult]:
        """
        Run OCR. Returns list of OCRResult with text, confidence, bbox.
        - Accepts BGR (OpenCV) or grayscale. Ensures uint8 and 3-channel.
        - Added memory safety checks and image size validation.
        - Cross-platform compatible OCR result parsing.
        """
        if self._ocr is None:
            logging.error("OCR engine not initialized. Call initialize() first.")
            return []

        try:
            # Input validation for cross-platform compatibility
            if image is None or image.size == 0:
                logging.warning("Empty image provided to OCR")
                return []

            # Check image dimensions for memory safety
            h, w = image.shape[:2]
            if h <= 0 or w <= 0:
                logging.warning(f"Invalid image dimensions: {w}x{h}")
                return []

            # Prevent excessive memory usage
            max_dimension = 4096  # 4K resolution limit
            if h > max_dimension or w > max_dimension:
                logging.warning(f"Image too large: {w}x{h}, resizing for memory safety")
                scale = min(max_dimension / w, max_dimension / h)
                new_w, new_h = int(w * scale), int(h * scale)
                image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
                logging.debug(f"Resized to: {new_w}x{new_h}")

            # Normalize dtype/shape for Paddle
            if image.dtype != np.uint8:
                image = image.astype(np.uint8)
            if image.ndim == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

            # Ensure contiguous memory layout (important for Windows)
            if not image.flags['C_CONTIGUOUS']:
                image = np.ascontiguousarray(image)

            # Cross-platform OCR inference
            logging.debug(f"Running OCR on {platform.system()} with image shape: {image.shape}")
            results = self._ocr.ocr(image)

            # Cross-platform result parsing
            ocr_results: List[OCRResult] = []
            if results and len(results) > 0:
                result = results[0]
                logging.debug(f"OCR result type: {type(result)}, length: {len(result) if result else 0}")

                if result is None:
                    logging.debug("OCR returned None result")
                    return ocr_results

                # Handle different result formats across PaddleOCR versions/platforms
                if hasattr(result, 'get') or isinstance(result, dict):
                    # Dictionary format (newer PaddleOCR versions)
                    logging.debug("Processing dictionary format OCR results")
                    rec_texts = result.get('rec_texts', [])
                    rec_scores = result.get('rec_scores', [])
                    rec_polys = result.get('rec_polys', [])

                    for i, text in enumerate(rec_texts):
                        if i < len(rec_scores) and i < len(rec_polys):
                            conf = rec_scores[i]
                            poly = rec_polys[i]

                            if conf < self.confidence_threshold or not text.strip():
                                continue

                            # Cross-platform bbox calculation
                            xs = [int(p[0]) for p in poly]
                            ys = [int(p[1]) for p in poly]
                            x, y = min(xs), min(ys)
                            w, h = max(xs) - x, max(ys) - y

                            ocr_results.append(OCRResult(text=text, confidence=float(conf), bbox=(x, y, w, h)))
                else:
                    # List format (traditional PaddleOCR format)
                    logging.debug("Processing list format OCR results")
                    for item in result:
                        try:
                            if len(item) == 2:
                                box, text_conf = item
                                if isinstance(text_conf, (list, tuple)) and len(text_conf) == 2:
                                    text, conf = text_conf
                                else:
                                    text = str(text_conf)
                                    conf = 1.0

                                if conf < self.confidence_threshold or not text.strip():
                                    continue

                                # Cross-platform bbox calculation
                                xs = [int(p[0]) for p in box]
                                ys = [int(p[1]) for p in box]
                                x, y = min(xs), min(ys)
                                w, h = max(xs) - x, max(ys) - y

                                ocr_results.append(OCRResult(text=text, confidence=float(conf), bbox=(x, y, w, h)))
                        except Exception as e:
                            logging.warning(f"Failed to process OCR result item {item}: {e}")
                            continue

            logging.debug(f"OCR extraction completed on {platform.system()}: {len(ocr_results)} results")
            return ocr_results

        except (MemoryError, RuntimeError, ValueError) as e:
            logging.error(f"PaddleOCR memory/runtime error on {platform.system()}: {e}")
            return []
        except Exception as e:
            logging.error(f"PaddleOCR inference failed on {platform.system()}: {e}")
            return []
