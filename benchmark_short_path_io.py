#!/usr/bin/env python3
"""
Issue #172: Short path I/O optimization benchmark

This script compares OCR performance between long/complex paths
(OneDrive, network drives, Japanese paths) and short ASCII paths
to identify I/O-related performance bottlenecks.
"""

import json
import logging
import platform
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.core.extractor.ocr import SimplePaddleOCREngine, OCRStageTimings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_test_video_frames() -> List[np.ndarray]:
    """Create test video frames with Japanese text for path comparison."""
    frames = []

    # Frame 1: Simple subtitle
    frame1 = np.ones((720, 1280, 3), dtype=np.uint8) * 255
    cv2.putText(
        frame1,
        "Short Path Test",
        (400, 650),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (0, 0, 0),
        3,
    )
    frames.append(frame1)

    # Frame 2: Medium complexity
    frame2 = np.ones((720, 1280, 3), dtype=np.uint8) * 255
    cv2.putText(
        frame2,
        "I/O Performance Analysis",
        (300, 620),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (0, 0, 0),
        2,
    )
    cv2.putText(
        frame2,
        "Path Length Impact Test",
        (320, 670),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (0, 0, 0),
        2,
    )
    frames.append(frame2)

    # Frame 3: Complex subtitle
    frame3 = np.ones((720, 1280, 3), dtype=np.uint8) * 255
    cv2.putText(
        frame3,
        "OneDrive vs Local SSD",
        (350, 600),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        2,
    )
    cv2.putText(
        frame3,
        "Network Drive vs C: Drive",
        (300, 640),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        2,
    )
    cv2.putText(
        frame3,
        "ASCII vs Unicode Path Test",
        (320, 680),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        2,
    )
    frames.append(frame3)

    return frames


def setup_test_paths(base_short: Path, base_long: Path) -> tuple[List[Path], List[Path]]:
    """Setup test files in both short and long path locations."""
    frames = create_test_video_frames()

    # Create directories
    base_short.mkdir(parents=True, exist_ok=True)
    base_long.mkdir(parents=True, exist_ok=True)

    short_paths = []
    long_paths = []

    for i, frame in enumerate(frames):
        # Short ASCII path (Issue #172 target)
        short_path = base_short / f"frame_{i+1}.png"
        cv2.imwrite(str(short_path), frame)
        short_paths.append(short_path)

        # Long/complex path (current problematic scenario)
        long_path = base_long / f"test_frame_{i+1}_long_filename_for_io_testing.png"
        cv2.imwrite(str(long_path), frame)
        long_paths.append(long_path)

        logger.info("Created test files: %s | %s", short_path.name, long_path.name)

    return short_paths, long_paths


def benchmark_path_performance(file_paths: List[Path], path_type: str, num_runs: int = 3) -> Dict:
    """Benchmark OCR performance for given file paths."""
    logger.info("=" * 70)
    logger.info("BENCHMARKING %s PATHS", path_type.upper())
    logger.info("Path type: %s", path_type)
    logger.info("Number of files: %d", len(file_paths))
    logger.info("Number of runs: %d", num_runs)
    logger.info("=" * 70)

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

    # Enable stage timing for detailed analysis
    engine.enable_stage_timing(True)

    # Run benchmarks
    all_results = []
    total_file_io_time = 0.0

    for run in range(num_runs):
        logger.info("Run %d/%d:", run + 1, num_runs)

        run_results = []
        run_io_time = 0.0

        for file_path in file_paths:
            # Measure file I/O time (key metric for Issue #172)
            io_start = time.perf_counter()
            image = cv2.imread(str(file_path))
            io_time = time.perf_counter() - io_start
            run_io_time += io_time

            if image is None:
                logger.warning("Failed to load image: %s", file_path)
                continue

            # Run OCR with timing
            results = engine.extract_text(image)
            timing = engine.get_last_timing_results()

            if timing:
                # Calculate total path length for analysis
                path_length = len(str(file_path))

                run_results.append(
                    {
                        "file_path": str(file_path),
                        "path_length": path_length,
                        "path_type": path_type,
                        "io_time": io_time,
                        "decode_time": timing.decode_time,
                        "detection_time": timing.detection_time,
                        "classification_time": timing.classification_time,
                        "recognition_time": timing.recognition_time,
                        "total_time": timing.total_time,
                        "text_regions_found": len(results),
                    }
                )

                logger.info(
                    "  %s: I/O=%.3fms, OCR=%.3fms, Path=%d chars",
                    file_path.name,
                    io_time * 1000,
                    timing.total_time * 1000,
                    path_length,
                )

        all_results.append(run_results)
        total_file_io_time += run_io_time
        logger.info("  Run %d completed - Total I/O time: %.3f ms", run + 1, run_io_time * 1000)

    # Calculate averages
    if all_results:
        # Aggregate all measurements
        all_timings: List[Dict] = []
        total_io_time = 0.0
        total_path_length = 0

        for run_data in all_results:
            for measurement in run_data:
                all_timings.append(measurement)
                total_io_time += float(measurement["io_time"])
                total_path_length += int(measurement["path_length"])

        if all_timings:
            avg_io = total_io_time / len(all_timings)
            avg_decode = sum(float(t["decode_time"]) for t in all_timings) / len(all_timings)
            avg_detection = sum(float(t["detection_time"]) for t in all_timings) / len(all_timings)
            avg_classification = sum(float(t["classification_time"]) for t in all_timings) / len(
                all_timings
            )
            avg_recognition = sum(float(t["recognition_time"]) for t in all_timings) / len(
                all_timings
            )
            avg_total = sum(float(t["total_time"]) for t in all_timings) / len(all_timings)
            avg_path_length = total_path_length / len(all_timings)

            logger.info("RESULTS SUMMARY for %s paths:", path_type)
            logger.info("  Average path length:   %d characters", int(avg_path_length))
            logger.info("  Average I/O time:      %.3f ms", avg_io * 1000)
            logger.info("  Average OCR time:      %.3f ms", avg_total * 1000)
            logger.info("  Total processing time: %.3f ms", (avg_io + avg_total) * 1000)

            # Performance breakdown
            total_processing = avg_io + avg_total
            if total_processing > 0:
                logger.info("Performance Distribution:")
                logger.info("  I/O overhead:          %.1f%%", (avg_io / total_processing) * 100)
                logger.info("  OCR processing:        %.1f%%", (avg_total / total_processing) * 100)

        # Prepare results for comparison
        results_summary = {
            "path_type": path_type,
            "platform": f"{platform.system()}/{platform.machine()}",
            "num_runs": num_runs,
            "num_measurements": len(all_timings),
            "avg_path_length": int(avg_path_length) if all_timings else 0,
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


def compare_path_performance(short_results: Dict, long_results: Dict) -> None:
    """Compare short vs long path performance and provide recommendations."""
    logger.info("=" * 70)
    logger.info("SHORT vs LONG PATH PERFORMANCE COMPARISON")
    logger.info("=" * 70)

    if not short_results or not long_results:
        logger.error("Missing benchmark data for comparison")
        return

    short_io = short_results["avg_file_io_ms"]
    short_ocr = short_results["avg_total_ocr_ms"]
    short_total = short_results["avg_total_processing_ms"]
    short_path_len = short_results["avg_path_length"]

    long_io = long_results["avg_file_io_ms"]
    long_ocr = long_results["avg_total_ocr_ms"]
    long_total = long_results["avg_total_processing_ms"]
    long_path_len = long_results["avg_path_length"]

    logger.info("SHORT PATH PERFORMANCE:")
    logger.info("  Average path length:  %d characters", short_path_len)
    logger.info("  File I/O time:        %.3f ms", short_io)
    logger.info("  OCR processing:       %.3f ms", short_ocr)
    logger.info("  Total time:           %.3f ms", short_total)

    logger.info("LONG PATH PERFORMANCE:")
    logger.info("  Average path length:  %d characters", long_path_len)
    logger.info("  File I/O time:        %.3f ms", long_io)
    logger.info("  OCR processing:       %.3f ms", long_ocr)
    logger.info("  Total time:           %.3f ms", long_total)

    # Calculate improvements from using short paths
    io_improvement = ((long_io - short_io) / long_io * 100) if long_io > 0 else 0
    ocr_improvement = ((long_ocr - short_ocr) / long_ocr * 100) if long_ocr > 0 else 0
    total_improvement = ((long_total - short_total) / long_total * 100) if long_total > 0 else 0

    logger.info("=" * 70)
    logger.info("PATH OPTIMIZATION IMPACT ANALYSIS:")
    logger.info(
        "  Path length reduction: %d → %d characters (%.1f%% shorter)",
        long_path_len,
        short_path_len,
        ((long_path_len - short_path_len) / long_path_len * 100) if long_path_len > 0 else 0,
    )
    logger.info(
        "  I/O time improvement:  %+.1f%% (%s%.3f ms)",
        io_improvement,
        "+" if io_improvement > 0 else "",
        long_io - short_io,
    )
    logger.info(
        "  OCR time change:       %+.1f%% (%s%.3f ms)",
        ocr_improvement,
        "+" if ocr_improvement > 0 else "",
        long_ocr - short_ocr,
    )
    logger.info(
        "  Total time improvement: %+.1f%% (%s%.3f ms)",
        total_improvement,
        "+" if total_improvement > 0 else "",
        long_total - short_total,
    )

    # Provide recommendations for Issue #172
    logger.info("=" * 70)
    logger.info("ISSUE #172 RECOMMENDATIONS:")

    if io_improvement > 10:
        logger.info("🚀 Significant I/O improvement detected (%.1f%%)", io_improvement)
        logger.info("   STRONGLY RECOMMEND: Use short ASCII paths like C:\\work\\input\\")
        logger.info("   Avoid: OneDrive, network drives, long folder structures")
    elif io_improvement > 5:
        logger.info("✅ Moderate I/O improvement detected (%.1f%%)", io_improvement)
        logger.info("   RECOMMEND: Consider using shorter paths for frequent processing")
    elif io_improvement > 1:
        logger.info("📊 Minor I/O improvement detected (%.1f%%)", io_improvement)
        logger.info("   Optional: Short paths provide small benefit")
    else:
        logger.info("ℹ️  Minimal I/O difference detected (%.1f%%)", io_improvement)
        logger.info("   Path length has minimal impact on this system")

    if total_improvement > 5:
        logger.info("💡 Overall processing improvement: %.1f%%", total_improvement)
        logger.info("   Path optimization is worthwhile for performance-critical workflows")

    logger.info("=" * 70)


def save_benchmark_results(results: Dict, output_file: Path) -> None:
    """Save benchmark results to JSON file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info("Results saved to: %s", output_file)


def cleanup_test_files(short_paths: List[Path], long_paths: List[Path]) -> None:
    """Clean up test files after benchmarking."""
    try:
        files_removed = 0

        # Remove only the specific files we created
        for file_path in short_paths + long_paths:
            if file_path.exists():
                file_path.unlink()
                files_removed += 1

        logger.info("Test files cleaned up: %d files removed", files_removed)

        # Only remove directories if they are empty (to avoid data loss)
        for dir_path in [
            short_paths[0].parent if short_paths else None,
            long_paths[0].parent if long_paths else None,
        ]:
            if dir_path and dir_path.exists():
                try:
                    # Only remove if directory is empty
                    dir_path.rmdir()
                    logger.info("Removed empty directory: %s", dir_path)
                except OSError:
                    # Directory not empty or other error - leave it alone
                    logger.debug("Directory not empty or cannot be removed: %s", dir_path)

    except Exception as e:
        logger.warning("Failed to clean up test files: %s", e)


def main() -> None:
    """Main function to run the short path I/O benchmark."""
    import argparse

    parser = argparse.ArgumentParser(description="Short path I/O optimization benchmark")
    parser.add_argument(
        "--short-base",
        type=Path,
        default=Path("C:/work/input") if platform.system() == "Windows" else Path("/tmp/short"),
        help="Base directory for short ASCII paths",
    )
    parser.add_argument(
        "--long-base",
        type=Path,
        default=(
            Path.home() / "Documents" / "very_long_folder_name_for_io_testing" / "input"
            if platform.system() == "Windows"
            else Path("/tmp/very_long_folder_name_for_io_testing_on_linux_system")
        ),
        help="Base directory for long/complex paths (defaults to user's Documents folder on Windows)",
    )
    parser.add_argument("--runs", type=int, default=3, help="Number of benchmark runs")
    parser.add_argument(
        "--output-short",
        type=Path,
        default=None,
        help="Output file for short path results",
    )
    parser.add_argument(
        "--output-long",
        type=Path,
        default=None,
        help="Output file for long path results",
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip cleanup of test files",
    )

    args = parser.parse_args()

    # Set default output filenames
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    if args.output_short is None:
        args.output_short = Path(f"path_benchmark_short_{timestamp}.json")
    if args.output_long is None:
        args.output_long = Path(f"path_benchmark_long_{timestamp}.json")

    logger.info("=" * 70)
    logger.info("Issue #172: Short Path I/O Optimization Benchmark")
    logger.info("Platform: %s %s", platform.system(), platform.machine())
    logger.info("Short path base: %s", args.short_base)
    logger.info("Long path base: %s", args.long_base)
    logger.info("=" * 70)

    # Initialize path variables for cleanup
    short_paths: List[Path] = []
    long_paths: List[Path] = []

    try:
        # Setup test files in both locations
        logger.info("Setting up test files...")
        short_paths, long_paths = setup_test_paths(args.short_base, args.long_base)

        # Benchmark short paths
        logger.info("Benchmarking SHORT paths...")
        short_results = benchmark_path_performance(short_paths, "short", args.runs)

        if short_results:
            save_benchmark_results(short_results, args.output_short)

        # Benchmark long paths
        logger.info("Benchmarking LONG paths...")
        long_results = benchmark_path_performance(long_paths, "long", args.runs)

        if long_results:
            save_benchmark_results(long_results, args.output_long)

        # Compare results
        if short_results and long_results:
            compare_path_performance(short_results, long_results)
        else:
            logger.error("Benchmark failed - insufficient data for comparison")

    finally:
        # Cleanup test files
        if not args.skip_cleanup:
            cleanup_test_files(short_paths, long_paths)

    logger.info("Issue #172 benchmark completed!")


if __name__ == "__main__":
    main()
