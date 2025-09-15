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
                 models_root: Optional[Path] = None) -> None:
        self.language = language
        self.confidence_threshold = confidence_threshold
        self.models_root = models_root  # if None, auto-discover under app/models/paddleocr
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
                "det_model_dir": str(det_dir),
                "rec_model_dir": str(rec_dir),
                "lang": lang,
                "use_angle_cls": True,
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
        """
        if self._ocr is None:
            logging.error("OCR engine not initialized. Call initialize() first.")
            return []

        try:
            # Normalize dtype/shape for Paddle
            if image.dtype != np.uint8:
                image = image.astype(np.uint8)
            if image.ndim == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

            # Directly pass image; PaddleOCR does its own preprocessing
            results = self._ocr.ocr(image)

            ocr_results: List[OCRResult] = []
            if results and results[0]:
                for box, (text, conf) in results[0]:
                    if conf < self.confidence_threshold or not text.strip():
                        continue
                    xs = [int(p[0]) for p in box]
                    ys = [int(p[1]) for p in box]
                    x, y = min(xs), min(ys)
                    w, h = max(xs) - x, max(ys) - y
                    ocr_results.append(OCRResult(text=text, confidence=float(conf), bbox=(x, y, w, h)))
            return ocr_results
        except Exception as e:
            logging.error(f"PaddleOCR inference failed: {e}")
            return []
