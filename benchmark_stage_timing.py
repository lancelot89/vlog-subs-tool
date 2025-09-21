#!/usr/bin/env python3
"""
Issue #170: Stage-by-stage OCR benchmark script for Windows/WSL comparison

This script demonstrates the stage-by-stage timing functionality
added to SimplePaddleOCREngine for identifying bottlenecks.
"""

import logging
import platform
import time
from pathlib import Path

import cv2
import numpy as np

from app.core.extractor.ocr import SimplePaddleOCREngine, OCRStageTimings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_test_image() -> np.ndarray:
    """Create a test image with Japanese text for OCR benchmarking."""
    # Create a white background image
    img = np.ones((400, 800, 3), dtype=np.uint8) * 255

    # Add some Japanese text (simulated)
    cv2.putText(img, "Test OCR Benchmark", (50, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 2)
    cv2.putText(img, "Stage Timing Analysis", (50, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    cv2.putText(img, "Windows vs WSL Performance", (50, 300),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    return img


def run_stage_benchmark() -> None:
    """Run the stage-by-stage OCR benchmark."""
    logger.info("=" * 60)
    logger.info("Issue #170: Stage-by-stage OCR Benchmark")
    logger.info("Platform: %s %s", platform.system(), platform.machine())
    logger.info("=" * 60)

    # Initialize OCR engine
    try:
        engine = SimplePaddleOCREngine(
            language="ja",
            confidence_threshold=0.5,
            max_batch_size=1,
            max_image_pixels=2048 * 2048,
            max_side_length=2048,
        )

        logger.info("Initializing PaddleOCR engine...")
        if not engine.initialize():
            logger.error("Failed to initialize OCR engine")
            return

        logger.info("OCR engine initialized successfully")

    except Exception as e:
        logger.error("Failed to create OCR engine: %s", e)
        return

    # Create test image
    logger.info("Creating test image...")
    test_image = create_test_image()

    # Run benchmark with timing enabled
    logger.info("Enabling stage-by-stage timing...")
    engine.enable_stage_timing(True)

    # Perform multiple runs for average timing
    num_runs = 3
    all_timings = []

    logger.info("Running %d benchmark iterations...", num_runs)

    for i in range(num_runs):
        logger.info("Run %d/%d:", i + 1, num_runs)

        # Run OCR
        results = engine.extract_text(test_image)

        # Get timing results
        timing = engine.get_last_timing_results()
        if timing:
            all_timings.append(timing)
            logger.info("  Found %d text regions", len(results))
        else:
            logger.warning("  No timing data available for run %d", i + 1)

    # Calculate averages
    if all_timings:
        logger.info("=" * 60)
        logger.info("AVERAGE STAGE TIMINGS (%d runs):", len(all_timings))

        avg_decode = sum(t.decode_time for t in all_timings) / len(all_timings)
        avg_detection = sum(t.detection_time for t in all_timings) / len(all_timings)
        avg_classification = sum(t.classification_time for t in all_timings) / len(all_timings)
        avg_recognition = sum(t.recognition_time for t in all_timings) / len(all_timings)
        avg_total = sum(t.total_time for t in all_timings) / len(all_timings)

        logger.info("  Decode/Preprocess: %.3f ms", avg_decode * 1000)
        logger.info("  Text Detection:    %.3f ms", avg_detection * 1000)
        logger.info("  Text Classification: %.3f ms", avg_classification * 1000)
        logger.info("  Text Recognition:  %.3f ms", avg_recognition * 1000)
        logger.info("  Total OCR Time:    %.3f ms", avg_total * 1000)

        if avg_total > 0:
            logger.info("STAGE BREAKDOWN:")
            logger.info("  Decode:    %.1f%%", (avg_decode / avg_total) * 100)
            logger.info("  Detection: %.1f%%", (avg_detection / avg_total) * 100)
            logger.info("  Classification: %.1f%%", (avg_classification / avg_total) * 100)
            logger.info("  Recognition: %.1f%%", (avg_recognition / avg_total) * 100)

    logger.info("=" * 60)
    logger.info("Benchmark completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_stage_benchmark()