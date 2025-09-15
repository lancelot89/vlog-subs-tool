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
                 models_root: Optional[Path] = None, max_batch_size: int = 1) -> None:
        self.language = language
        self.confidence_threshold = confidence_threshold
        self.models_root = models_root  # if None, auto-discover under app/models/paddleocr
        self.max_batch_size = max_batch_size  # Limit batch processing to prevent memory issues
        self._ocr = None

    # ---------- path resolution ----------
    def _resolve_models_root(self) -> Path:
        """
        Resolve the app's bundled paddleocr models directory.
        Search precedence:
          1) explicit models_root if provided
          2) env PADDLE_MODELS_DIR (absolute/relative allowed)
          3) ascend up to 6 parents from this file to find 'app/models/paddleocr'
          4) cwd/app/models/paddleocr
        """
        # 1) explicit arg
        if self.models_root and (self.models_root / "PP-OCRv5_server_det").exists():
            return self.models_root

        # 2) env var
        env_dir = os.environ.get("PADDLE_MODELS_DIR")
        if env_dir:
            p = Path(env_dir).resolve()
            if (p / "PP-OCRv5_server_det").exists():
                return p

        # 3) ascend parents
        here = Path(__file__).resolve()
        for parent in [here.parent] + list(here.parents)[:6]:
            candidate = parent / "app" / "models" / "paddleocr"
            if (candidate / "PP-OCRv5_server_det").exists() and (candidate / "PP-OCRv5_server_rec").exists():
                return candidate

        # 4) cwd fallback
        candidate = Path.cwd() / "app" / "models" / "paddleocr"
        if (candidate / "PP-OCRv5_server_det").exists() and (candidate / "PP-OCRv5_server_rec").exists():
            return candidate

        raise FileNotFoundError(
            "Bundled PaddleOCR models not found. Expected at app/models/paddleocr/"
            " with PP-OCRv5_server_det and PP-OCRv5_server_rec subdirs."
        )

    # ---------- init ----------
    def initialize(self) -> bool:
        """
        Initialize PaddleOCR with bundled models. CPU-only.
        """
        try:
            # CPU only setup (avoid accidental GPU usage / CUDA problems)
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
            os.environ.setdefault("FLAGS_call_stack_level", "2")

            root = self._resolve_models_root()
            det_dir = root / "PP-OCRv5_server_det"
            rec_dir = root / "PP-OCRv5_server_rec"

            lang = "japan" if self.language.lower() in {"ja", "jpn", "japanese"} else self.language

            kwargs = {
                "text_detection_model_dir": str(det_dir),
                "text_recognition_model_dir": str(rec_dir),
                "lang": lang,
                "use_textline_orientation": True,
                "text_det_limit_side_len": 1536,  # Limit detection resolution
                "text_det_limit_type": "max",  # Max dimension limit
            }

            logging.debug(f"PaddleOCR init kwargs: {kwargs}")
            self._ocr = PaddleOCR(**kwargs)
            logging.info("PaddleOCR initialized with bundled models.")
            return True
        except Exception as e:
            logging.error(f"PaddleOCR initialization failed: {e}")
            self._ocr = None
            return False

    # ---------- inference ----------
    def extract_text(self, image: np.ndarray) -> List[OCRResult]:
        """
        Run OCR. Returns list of OCRResult with text, confidence, bbox.
        - Accepts BGR (OpenCV) or grayscale. Ensures uint8 and 3-channel.
        - Added memory safety checks and image size validation.
        """
        if self._ocr is None:
            logging.error("OCR engine not initialized. Call initialize() first.")
            return []

        try:
            # Input validation
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

            # Ensure contiguous memory layout
            if not image.flags['C_CONTIGUOUS']:
                image = np.ascontiguousarray(image)

            # Directly pass image; PaddleOCR does its own preprocessing
            results = self._ocr.ocr(image)

            ocr_results: List[OCRResult] = []
            if results and len(results) > 0:
                result = results[0]

                # 新しいPaddleOCRの結果形式（辞書形式）に対応
                if hasattr(result, 'get') or isinstance(result, dict):
                    # 辞書形式の結果を処理
                    rec_texts = result.get('rec_texts', [])
                    rec_scores = result.get('rec_scores', [])
                    rec_polys = result.get('rec_polys', [])

                    for i, text in enumerate(rec_texts):
                        if i < len(rec_scores) and i < len(rec_polys):
                            conf = rec_scores[i]
                            poly = rec_polys[i]

                            if conf < self.confidence_threshold or not text.strip():
                                continue

                            # バウンディングボックスの計算
                            xs = [int(p[0]) for p in poly]
                            ys = [int(p[1]) for p in poly]
                            x, y = min(xs), min(ys)
                            w, h = max(xs) - x, max(ys) - y

                            ocr_results.append(OCRResult(text=text, confidence=float(conf), bbox=(x, y, w, h)))
                else:
                    # 従来形式（リスト）の結果を処理
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

                                xs = [int(p[0]) for p in box]
                                ys = [int(p[1]) for p in box]
                                x, y = min(xs), min(ys)
                                w, h = max(xs) - x, max(ys) - y

                                ocr_results.append(OCRResult(text=text, confidence=float(conf), bbox=(x, y, w, h)))
                        except Exception as e:
                            logging.warning(f"Failed to process OCR result item {item}: {e}")
                            continue

            return ocr_results
        except (MemoryError, RuntimeError, ValueError) as e:
            logging.error(f"PaddleOCR memory/runtime error: {e}")
            return []
        except Exception as e:
            logging.error(f"PaddleOCR inference failed: {e}")
            return []
