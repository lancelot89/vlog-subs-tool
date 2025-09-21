#!/usr/bin/env python3
"""
Issue #171: Windows Defender exclusion impact benchmark

This script helps measure the performance impact of Windows Defender
real-time protection on OCR processing speed by comparing before/after
exclusion measurements.
"""

import json
import logging
import platform
import time
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

from app.core.extractor.ocr import SimplePaddleOCREngine, OCRStageTimings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_test_images() -> List[np.ndarray]:
    """Create multiple test images with varying complexity for I/O testing."""
    images = []

    # Simple image
    img1 = np.ones((200, 400, 3), dtype=np.uint8) * 255
    cv2.putText(img1, "Simple Test", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    images.append(img1)

    # Medium complexity image
    img2 = np.ones((400, 800, 3), dtype=np.uint8) * 255
    cv2.putText(
        img2, "Windows Defender Test", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 2
    )
    cv2.putText(
        img2, "I/O Performance Analysis", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2
    )
    cv2.putText(
        img2, "Real-time Protection Impact", (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2
    )
    images.append(img2)

    # Complex image with more text
    img3 = np.ones((600, 1200, 3), dtype=np.uint8) * 255
    for i in range(5):
        y_pos = 100 + i * 80
        cv2.putText(
            img3,
            f"Line {i+1}: Defender exclusion test",
            (50, y_pos),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 0),
            2,
        )
    images.append(img3)

    return images


def save_test_images_to_workspace(workspace_dir: Path) -> List[Path]:
    """Save test images to workspace directory for I/O testing."""
    workspace_dir.mkdir(parents=True, exist_ok=True)

    images = create_test_images()
    image_paths = []

    for i, img in enumerate(images):
        img_path = workspace_dir / f"test_image_{i+1}.png"
        cv2.imwrite(str(img_path), img)
        image_paths.append(img_path)
        logger.info("Saved test image: %s", img_path)

    return image_paths


def run_defender_benchmark(
    workspace_dir: Path, num_runs: int = 5, exclusion_status: str = "unknown"
) -> Dict:
    """Run OCR benchmark and measure I/O performance impact."""
    logger.info("=" * 70)
    logger.info("Issue #171: Windows Defender Exclusion Impact Benchmark")
    logger.info("Platform: %s %s", platform.system(), platform.machine())
    logger.info("Exclusion Status: %s", exclusion_status)
    logger.info("Workspace: %s", workspace_dir)
    logger.info("=" * 70)

    if platform.system() != "Windows":
        logger.warning("This benchmark is designed for Windows systems")
        logger.warning("Running on %s - results may not be representative", platform.system())

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
            return {}

        logger.info("OCR engine initialized successfully")

    except Exception as e:
        logger.error("Failed to create OCR engine: %s", e)
        return {}

    # Create workspace directory and save test images
    logger.info("Creating workspace and test images...")
    image_paths = save_test_images_to_workspace(workspace_dir)

    # Enable stage timing for detailed analysis
    engine.enable_stage_timing(True)

    # Run benchmarks
    all_results = []
    file_io_times = []

    logger.info("Running %d benchmark iterations...", num_runs)

    for run in range(num_runs):
        logger.info("Run %d/%d:", run + 1, num_runs)

        run_results = []
        run_io_time = 0.0

        for img_path in image_paths:
            # Measure file I/O time (potentially affected by Defender)
            io_start = time.perf_counter()
            image = cv2.imread(str(img_path))
            io_time = time.perf_counter() - io_start
            run_io_time += io_time

            if image is None:
                logger.warning("Failed to load image: %s", img_path)
                continue

            # Run OCR
            results = engine.extract_text(image)
            timing = engine.get_last_timing_results()

            if timing:
                run_results.append(
                    {
                        "image_path": str(img_path),
                        "image_size": image.shape,
                        "io_time": io_time,
                        "decode_time": timing.decode_time,
                        "detection_time": timing.detection_time,
                        "classification_time": timing.classification_time,
                        "recognition_time": timing.recognition_time,
                        "total_time": timing.total_time,
                        "text_regions_found": len(results),
                    }
                )

        all_results.append(run_results)
        file_io_times.append(run_io_time)
        logger.info("  Run %d completed - Total I/O time: %.3f ms", run + 1, run_io_time * 1000)

    # Calculate averages
    if all_results:
        logger.info("=" * 70)
        logger.info("DEFENDER EXCLUSION IMPACT ANALYSIS:")

        # Aggregate all measurements
        all_timings = []
        total_io_time = 0.0

        for run_data in all_results:
            for measurement in run_data:
                all_timings.append(measurement)
                total_io_time += measurement["io_time"]

        if all_timings:
            avg_io = total_io_time / len(all_timings)
            avg_decode = sum(t["decode_time"] for t in all_timings) / len(all_timings)
            avg_detection = sum(t["detection_time"] for t in all_timings) / len(all_timings)
            avg_classification = sum(t["classification_time"] for t in all_timings) / len(
                all_timings
            )
            avg_recognition = sum(t["recognition_time"] for t in all_timings) / len(all_timings)
            avg_total = sum(t["total_time"] for t in all_timings) / len(all_timings)

            logger.info("Average Timings (%d measurements):", len(all_timings))
            logger.info("  File I/O:          %.3f ms", avg_io * 1000)
            logger.info("  Decode/Preprocess: %.3f ms", avg_decode * 1000)
            logger.info("  Detection:         %.3f ms", avg_detection * 1000)
            logger.info("  Classification:    %.3f ms", avg_classification * 1000)
            logger.info("  Recognition:       %.3f ms", avg_recognition * 1000)
            logger.info("  Total OCR:         %.3f ms", avg_total * 1000)

            # Calculate percentages
            total_processing = avg_io + avg_total
            if total_processing > 0:
                logger.info("Time Distribution:")
                logger.info("  I/O:               %.1f%%", (avg_io / total_processing) * 100)
                logger.info("  OCR Processing:    %.1f%%", (avg_total / total_processing) * 100)

        # Prepare results for comparison
        results_summary = {
            "exclusion_status": exclusion_status,
            "platform": f"{platform.system()}/{platform.machine()}",
            "workspace_path": str(workspace_dir),
            "num_runs": num_runs,
            "num_measurements": len(all_timings),
            "avg_file_io_ms": avg_io * 1000 if all_timings else 0,
            "avg_decode_ms": avg_decode * 1000 if all_timings else 0,
            "avg_detection_ms": avg_detection * 1000 if all_timings else 0,
            "avg_classification_ms": avg_classification * 1000 if all_timings else 0,
            "avg_recognition_ms": avg_recognition * 1000 if all_timings else 0,
            "avg_total_ocr_ms": avg_total * 1000 if all_timings else 0,
            "avg_total_processing_ms": (avg_io + avg_total) * 1000 if all_timings else 0,
            "detailed_results": all_results,
        }

        return results_summary

    return {}


def save_benchmark_results(results: Dict, output_file: Path) -> None:
    """Save benchmark results to JSON file for comparison."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info("Results saved to: %s", output_file)


def compare_exclusion_results(before_file: Path, after_file: Path) -> None:
    """Compare before/after exclusion results and show impact analysis."""
    logger.info("=" * 70)
    logger.info("WINDOWS DEFENDER EXCLUSION IMPACT COMPARISON")
    logger.info("=" * 70)

    try:
        with open(before_file, "r", encoding="utf-8") as f:
            before_data = json.load(f)

        with open(after_file, "r", encoding="utf-8") as f:
            after_data = json.load(f)

        logger.info("Before Exclusion:")
        logger.info("  File I/O:       %.3f ms", before_data["avg_file_io_ms"])
        logger.info("  Total OCR:      %.3f ms", before_data["avg_total_ocr_ms"])
        logger.info("  Total Process:  %.3f ms", before_data["avg_total_processing_ms"])

        logger.info("After Exclusion:")
        logger.info("  File I/O:       %.3f ms", after_data["avg_file_io_ms"])
        logger.info("  Total OCR:      %.3f ms", after_data["avg_total_ocr_ms"])
        logger.info("  Total Process:  %.3f ms", after_data["avg_total_processing_ms"])

        # Calculate improvements
        io_improvement = (
            (
                (before_data["avg_file_io_ms"] - after_data["avg_file_io_ms"])
                / before_data["avg_file_io_ms"]
                * 100
            )
            if before_data["avg_file_io_ms"] > 0
            else 0
        )

        ocr_improvement = (
            (
                (before_data["avg_total_ocr_ms"] - after_data["avg_total_ocr_ms"])
                / before_data["avg_total_ocr_ms"]
                * 100
            )
            if before_data["avg_total_ocr_ms"] > 0
            else 0
        )

        total_improvement = (
            (
                (before_data["avg_total_processing_ms"] - after_data["avg_total_processing_ms"])
                / before_data["avg_total_processing_ms"]
                * 100
            )
            if before_data["avg_total_processing_ms"] > 0
            else 0
        )

        logger.info("=" * 70)
        logger.info("IMPROVEMENT ANALYSIS:")
        logger.info(
            "  File I/O:       %+.1f%% (%s%.3f ms)",
            io_improvement,
            "+" if io_improvement > 0 else "",
            before_data["avg_file_io_ms"] - after_data["avg_file_io_ms"],
        )

        logger.info(
            "  OCR Processing: %+.1f%% (%s%.3f ms)",
            ocr_improvement,
            "+" if ocr_improvement > 0 else "",
            before_data["avg_total_ocr_ms"] - after_data["avg_total_ocr_ms"],
        )

        logger.info(
            "  Total Process:  %+.1f%% (%s%.3f ms)",
            total_improvement,
            "+" if total_improvement > 0 else "",
            before_data["avg_total_processing_ms"] - after_data["avg_total_processing_ms"],
        )

        # Recommendations
        logger.info("=" * 70)
        logger.info("RECOMMENDATIONS:")

        if total_improvement > 5:
            logger.info("✅ Significant improvement detected (%.1f%%)", total_improvement)
            logger.info("   Recommend adding workspace to Defender exclusions")
        elif total_improvement > 1:
            logger.info("⚠️  Moderate improvement detected (%.1f%%)", total_improvement)
            logger.info("   Consider adding workspace to Defender exclusions")
        else:
            logger.info("ℹ️  Minimal impact detected (%.1f%%)", total_improvement)
            logger.info("   Defender exclusion may not be necessary")

        if io_improvement > 10:
            logger.info("📁 File I/O significantly improved - Defender was impacting disk access")

        logger.info("=" * 70)

    except Exception as e:
        logger.error("Failed to compare results: %s", e)


def main() -> None:
    """Main function to run the Defender exclusion benchmark."""
    import argparse

    parser = argparse.ArgumentParser(description="Windows Defender exclusion impact benchmark")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("C:/work/vlog-subs-tool/workspace"),
        help="Workspace directory for test files",
    )
    parser.add_argument("--runs", type=int, default=5, help="Number of benchmark runs")
    parser.add_argument(
        "--exclusion-status",
        choices=["before", "after", "unknown"],
        default="unknown",
        help="Whether this is before or after adding Defender exclusions",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for results (auto-generated if not specified)",
    )
    parser.add_argument(
        "--compare-before",
        type=Path,
        default=None,
        help="Compare with previous 'before' results file",
    )
    parser.add_argument(
        "--compare-after",
        type=Path,
        default=None,
        help="Compare with previous 'after' results file",
    )

    args = parser.parse_args()

    # Set default output filename
    if args.output is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        args.output = Path(f"defender_benchmark_{args.exclusion_status}_{timestamp}.json")

    # Run benchmark
    logger.info("Starting Windows Defender exclusion impact benchmark...")
    logger.info("Arguments: %s", vars(args))

    results = run_defender_benchmark(args.workspace, args.runs, args.exclusion_status)

    if results:
        save_benchmark_results(results, args.output)

        # Perform comparison if requested
        if args.compare_before and args.compare_after:
            compare_exclusion_results(args.compare_before, args.compare_after)
    else:
        logger.error("Benchmark failed - no results to save")


if __name__ == "__main__":
    main()
