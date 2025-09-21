#!/usr/bin/env python3
"""
Issue #173: OpenCV decode vs ffmpeg CLI pre-extraction comparison

This script compares video decoding performance between:
1. Current OpenCV VideoCapture approach (frame-by-frame decoding)
2. ffmpeg CLI pre-extraction approach (bulk frame extraction + OCR)

Measures total time, decode time, and OCR time for each method.
"""

import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

from app.core.extractor.ocr import OCRStageTimings, SimplePaddleOCREngine

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_test_video(output_path: Path, duration_seconds: int = 5, fps: int = 1) -> bool:
    """Create a test video with subtitle-like frames for benchmarking."""
    try:
        # Video properties
        width, height = 1280, 720
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

        total_frames = duration_seconds * fps
        logger.info("Creating test video: %d frames at %d fps", total_frames, fps)

        for frame_num in range(total_frames):
            # Create white background
            frame = np.ones((height, width, 3), dtype=np.uint8) * 255

            # Add subtitle-like text at bottom
            subtitle_text = f"Frame {frame_num + 1}: OpenCV vs ffmpeg test"
            cv2.putText(
                frame,
                subtitle_text,
                (50, height - 100),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 0, 0),
                2,
            )

            # Add timestamp
            timestamp = f"Time: {frame_num / fps:.1f}s"
            cv2.putText(
                frame,
                timestamp,
                (50, height - 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (128, 128, 128),
                2,
            )

            writer.write(frame)

        writer.release()

        if output_path.exists():
            logger.info(
                "Test video created: %s (%.2f MB)",
                output_path,
                output_path.stat().st_size / 1024 / 1024,
            )
            return True
        else:
            logger.error("Failed to create test video")
            return False

    except Exception as e:
        logger.error("Error creating test video: %s", e)
        return False


def benchmark_opencv_method(video_path: Path, ocr_engine: SimplePaddleOCREngine) -> Dict:
    """Benchmark the current OpenCV VideoCapture method."""
    logger.info("=== BENCHMARKING OPENCV METHOD ===")

    start_time = time.perf_counter()

    # Open video
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error("Failed to open video: %s", video_path)
        return {}

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    logger.info("Video info: %d frames, %.2f fps", total_frames, fps)

    # Timing containers
    decode_times = []
    ocr_times = []
    frame_results = []

    frame_count = 0

    while True:
        # Measure decode time
        decode_start = time.perf_counter()
        ret, frame = cap.read()
        decode_time = time.perf_counter() - decode_start

        if not ret:
            break

        decode_times.append(decode_time)

        # Measure OCR time
        ocr_start = time.perf_counter()
        results = ocr_engine.extract_text(frame)
        timing = ocr_engine.get_last_timing_results()
        ocr_time = time.perf_counter() - ocr_start

        ocr_times.append(ocr_time)

        frame_results.append(
            {
                "frame_number": frame_count,
                "decode_time": decode_time,
                "ocr_time": ocr_time,
                "text_regions": len(results),
                "stage_timing": (
                    {
                        "decode": timing.decode_time if timing else 0,
                        "detection": timing.detection_time if timing else 0,
                        "classification": timing.classification_time if timing else 0,
                        "recognition": timing.recognition_time if timing else 0,
                        "total": timing.total_time if timing else 0,
                    }
                    if timing
                    else None
                ),
            }
        )

        frame_count += 1

        if frame_count % 10 == 0:
            logger.info("Processed %d/%d frames", frame_count, total_frames)

    cap.release()

    total_time = time.perf_counter() - start_time

    # Calculate statistics
    total_decode_time = sum(decode_times)
    total_ocr_time = sum(ocr_times)
    avg_decode_time = total_decode_time / len(decode_times) if decode_times else 0
    avg_ocr_time = total_ocr_time / len(ocr_times) if ocr_times else 0

    logger.info("OpenCV Method Results:")
    logger.info("  Total time:        %.3f s", total_time)
    logger.info(
        "  Total decode time: %.3f s (%.1f%%)",
        total_decode_time,
        (total_decode_time / total_time) * 100 if total_time > 0 else 0,
    )
    logger.info(
        "  Total OCR time:    %.3f s (%.1f%%)",
        total_ocr_time,
        (total_ocr_time / total_time) * 100 if total_time > 0 else 0,
    )
    logger.info("  Avg decode/frame:  %.3f ms", avg_decode_time * 1000)
    logger.info("  Avg OCR/frame:     %.3f ms", avg_ocr_time * 1000)
    logger.info("  Frames processed:  %d", frame_count)

    return {
        "method": "opencv",
        "total_time": total_time,
        "total_decode_time": total_decode_time,
        "total_ocr_time": total_ocr_time,
        "avg_decode_time": avg_decode_time,
        "avg_ocr_time": avg_ocr_time,
        "frames_processed": frame_count,
        "decode_percentage": (total_decode_time / total_time) * 100 if total_time > 0 else 0,
        "ocr_percentage": (total_ocr_time / total_time) * 100 if total_time > 0 else 0,
        "frame_results": frame_results,
    }


def benchmark_ffmpeg_method(
    video_path: Path, ocr_engine: SimplePaddleOCREngine, temp_dir: Path
) -> Dict:
    """Benchmark the ffmpeg CLI pre-extraction method."""
    logger.info("=== BENCHMARKING FFMPEG METHOD ===")

    start_time = time.perf_counter()

    # Create frames directory
    frames_dir = temp_dir / "ffmpeg_frames"
    frames_dir.mkdir(exist_ok=True)

    # ffmpeg command for frame extraction
    ffmpeg_cmd = [
        "ffmpeg",
        "-hwaccel",
        "auto",
        "-i",
        str(video_path),
        "-vsync",
        "0",
        "-qscale:v",
        "2",
        "-y",  # overwrite existing files
        str(frames_dir / "%06d.jpg"),
    ]

    logger.info("Running ffmpeg extraction: %s", " ".join(ffmpeg_cmd))

    # Measure ffmpeg extraction time
    extraction_start = time.perf_counter()

    try:
        result = subprocess.run(
            ffmpeg_cmd, capture_output=True, text=True, check=True, timeout=60  # 60 second timeout
        )
        logger.info("ffmpeg stderr: %s", result.stderr if result.stderr else "No output")
    except subprocess.CalledProcessError as e:
        logger.error("ffmpeg failed: %s", e.stderr)
        return {}
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out")
        return {}
    except FileNotFoundError:
        logger.error("ffmpeg not found. Please install ffmpeg.")
        return {}

    extraction_time = time.perf_counter() - extraction_start

    # Get list of extracted frames
    frame_files = sorted(frames_dir.glob("*.jpg"))

    logger.info("ffmpeg extracted %d frames in %.3f s", len(frame_files), extraction_time)

    if not frame_files:
        logger.error("No frames extracted by ffmpeg")
        return {}

    # Measure OCR processing time on extracted frames
    ocr_start = time.perf_counter()

    ocr_times = []
    frame_results = []

    for i, frame_file in enumerate(frame_files):
        # Load image (this is very fast compared to video decoding)
        load_start = time.perf_counter()
        image = cv2.imread(str(frame_file))
        load_time = time.perf_counter() - load_start

        if image is None:
            logger.warning("Failed to load frame: %s", frame_file)
            continue

        # Measure OCR time
        frame_ocr_start = time.perf_counter()
        results = ocr_engine.extract_text(image)
        timing = ocr_engine.get_last_timing_results()
        frame_ocr_time = time.perf_counter() - frame_ocr_start

        ocr_times.append(frame_ocr_time)

        frame_results.append(
            {
                "frame_number": i,
                "frame_file": str(frame_file),
                "load_time": load_time,
                "ocr_time": frame_ocr_time,
                "text_regions": len(results),
                "stage_timing": (
                    {
                        "decode": timing.decode_time if timing else 0,
                        "detection": timing.detection_time if timing else 0,
                        "classification": timing.classification_time if timing else 0,
                        "recognition": timing.recognition_time if timing else 0,
                        "total": timing.total_time if timing else 0,
                    }
                    if timing
                    else None
                ),
            }
        )

        if (i + 1) % 10 == 0:
            logger.info("Processed %d/%d frames", i + 1, len(frame_files))

    total_ocr_time = time.perf_counter() - ocr_start
    total_time = time.perf_counter() - start_time

    # Calculate statistics
    avg_ocr_time = sum(ocr_times) / len(ocr_times) if ocr_times else 0
    avg_load_time = (
        sum(r["load_time"] for r in frame_results) / len(frame_results) if frame_results else 0
    )

    logger.info("ffmpeg Method Results:")
    logger.info("  Total time:         %.3f s", total_time)
    logger.info(
        "  Extraction time:    %.3f s (%.1f%%)",
        extraction_time,
        (extraction_time / total_time) * 100 if total_time > 0 else 0,
    )
    logger.info(
        "  OCR processing:     %.3f s (%.1f%%)",
        total_ocr_time,
        (total_ocr_time / total_time) * 100 if total_time > 0 else 0,
    )
    logger.info("  Avg load/frame:     %.3f ms", avg_load_time * 1000)
    logger.info("  Avg OCR/frame:      %.3f ms", avg_ocr_time * 1000)
    logger.info("  Frames processed:   %d", len(frame_files))

    return {
        "method": "ffmpeg",
        "total_time": total_time,
        "extraction_time": extraction_time,
        "total_ocr_time": total_ocr_time,
        "avg_load_time": avg_load_time,
        "avg_ocr_time": avg_ocr_time,
        "frames_processed": len(frame_files),
        "extraction_percentage": (extraction_time / total_time) * 100 if total_time > 0 else 0,
        "ocr_percentage": (total_ocr_time / total_time) * 100 if total_time > 0 else 0,
        "frame_results": frame_results,
    }


def compare_methods(opencv_results: Dict, ffmpeg_results: Dict) -> None:
    """Compare the two methods and provide recommendations."""
    logger.info("=" * 70)
    logger.info("OPENCV vs FFMPEG DECODE COMPARISON")
    logger.info("=" * 70)

    if not opencv_results or not ffmpeg_results:
        logger.error("Missing benchmark data for comparison")
        return

    # Extract key metrics
    opencv_total = opencv_results["total_time"]
    opencv_decode = opencv_results["total_decode_time"]
    opencv_ocr = opencv_results["total_ocr_time"]

    ffmpeg_total = ffmpeg_results["total_time"]
    ffmpeg_extract = ffmpeg_results["extraction_time"]
    ffmpeg_ocr = ffmpeg_results["total_ocr_time"]

    logger.info("PERFORMANCE COMPARISON:")
    logger.info("  OpenCV Method:")
    logger.info("    Total time:    %.3f s", opencv_total)
    logger.info(
        "    Decode time:   %.3f s (%.1f%%)", opencv_decode, opencv_results["decode_percentage"]
    )
    logger.info("    OCR time:      %.3f s (%.1f%%)", opencv_ocr, opencv_results["ocr_percentage"])

    logger.info("  ffmpeg Method:")
    logger.info("    Total time:    %.3f s", ffmpeg_total)
    logger.info(
        "    Extract time:  %.3f s (%.1f%%)",
        ffmpeg_extract,
        ffmpeg_results["extraction_percentage"],
    )
    logger.info("    OCR time:      %.3f s (%.1f%%)", ffmpeg_ocr, ffmpeg_results["ocr_percentage"])

    # Calculate improvements
    total_improvement = (
        ((opencv_total - ffmpeg_total) / opencv_total * 100) if opencv_total > 0 else 0
    )
    decode_vs_extract = (
        ((opencv_decode - ffmpeg_extract) / opencv_decode * 100) if opencv_decode > 0 else 0
    )

    logger.info("=" * 70)
    logger.info("IMPROVEMENT ANALYSIS:")
    logger.info(
        "  Total time improvement: %+.1f%% (%s%.3f s)",
        total_improvement,
        "+" if total_improvement > 0 else "",
        opencv_total - ffmpeg_total,
    )
    logger.info(
        "  Decode vs Extract:      %+.1f%% (%s%.3f s)",
        decode_vs_extract,
        "+" if decode_vs_extract > 0 else "",
        opencv_decode - ffmpeg_extract,
    )

    # Provide recommendations for Issue #173
    logger.info("=" * 70)
    logger.info("ISSUE #173 RECOMMENDATIONS:")

    if total_improvement > 20:
        logger.info("🚀 Significant improvement with ffmpeg (%.1f%%)", total_improvement)
        logger.info("   RECOMMEND: Switch to ffmpeg pre-extraction method")
        logger.info("   Benefit: Substantial decode time reduction")
    elif total_improvement > 10:
        logger.info("✅ Moderate improvement with ffmpeg (%.1f%%)", total_improvement)
        logger.info("   RECOMMEND: Consider ffmpeg for batch processing")
        logger.info("   Benefit: Improved decode performance")
    elif total_improvement > 0:
        logger.info("📊 Minor improvement with ffmpeg (%.1f%%)", total_improvement)
        logger.info("   CONSIDER: ffmpeg for specific use cases")
    else:
        logger.info("⚖️  OpenCV performs better or similarly (%.1f%%)", abs(total_improvement))
        logger.info("   RECOMMEND: Continue with OpenCV method")
        logger.info("   Benefit: Simpler pipeline, no external dependencies")

    # Decode-specific analysis
    if decode_vs_extract > 50:
        logger.info("💡 Decode is a major bottleneck - ffmpeg extraction significantly faster")
    elif decode_vs_extract > 20:
        logger.info("💡 Moderate decode bottleneck - ffmpeg provides meaningful improvement")
    else:
        logger.info("💡 Decode is not the main bottleneck - focus on other optimizations")

    logger.info("=" * 70)


def save_comparison_results(opencv_results: Dict, ffmpeg_results: Dict, output_file: Path) -> None:
    """Save comparison results to JSON file."""
    comparison_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": f"{platform.system()}/{platform.machine()}",
        "opencv_results": opencv_results,
        "ffmpeg_results": ffmpeg_results,
        "summary": {
            "opencv_total_time": opencv_results.get("total_time", 0),
            "ffmpeg_total_time": ffmpeg_results.get("total_time", 0),
            "improvement_percentage": (
                (
                    (opencv_results.get("total_time", 0) - ffmpeg_results.get("total_time", 0))
                    / opencv_results.get("total_time", 1)
                    * 100
                )
                if opencv_results.get("total_time", 0) > 0
                else 0
            ),
            "decode_vs_extract_improvement": (
                (
                    (
                        opencv_results.get("total_decode_time", 0)
                        - ffmpeg_results.get("extraction_time", 0)
                    )
                    / opencv_results.get("total_decode_time", 1)
                    * 100
                )
                if opencv_results.get("total_decode_time", 0) > 0
                else 0
            ),
        },
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(comparison_data, f, indent=2, ensure_ascii=False)

    logger.info("Comparison results saved to: %s", output_file)


def cleanup_temp_files(temp_dir: Path) -> None:
    """Clean up temporary files."""
    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        logger.info("Temporary files cleaned up")
    except Exception as e:
        logger.warning("Failed to clean up temp files: %s", e)


def main() -> None:
    """Main function to run the decode comparison benchmark."""
    import argparse

    parser = argparse.ArgumentParser(description="OpenCV vs ffmpeg decode comparison benchmark")
    parser.add_argument(
        "--input-video",
        type=Path,
        default=None,
        help="Input video file (if not provided, a test video will be created)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=10,
        help="Test video duration in seconds (only used if creating test video)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=1,
        help="Test video FPS (only used if creating test video)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for comparison results",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary files for inspection",
    )

    args = parser.parse_args()

    # Set default output filename
    if args.output is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        args.output = Path(f"decode_comparison_{timestamp}.json")

    logger.info("=" * 70)
    logger.info("Issue #173: OpenCV vs ffmpeg Decode Comparison")
    logger.info("Platform: %s %s", platform.system(), platform.machine())
    logger.info("=" * 70)

    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="decode_comparison_"))
    logger.info("Temporary directory: %s", temp_dir)

    try:
        # Determine input video
        if args.input_video and args.input_video.exists():
            video_path = args.input_video
            logger.info("Using provided video: %s", video_path)
        else:
            # Create test video
            video_path = temp_dir / "test_video.mp4"
            logger.info("Creating test video: %s", video_path)
            if not create_test_video(video_path, args.duration, args.fps):
                logger.error("Failed to create test video")
                return

        # Initialize OCR engine
        logger.info("Initializing OCR engine...")
        ocr_engine = SimplePaddleOCREngine(
            language="ja",
            confidence_threshold=0.5,
            max_batch_size=1,
            max_image_pixels=2048 * 2048,
            max_side_length=2048,
        )

        if not ocr_engine.initialize():
            logger.error("Failed to initialize OCR engine")
            return

        # Enable stage timing for detailed analysis
        ocr_engine.enable_stage_timing(True)

        # Run benchmarks
        logger.info("Starting decode comparison benchmarks...")

        # Benchmark OpenCV method
        opencv_results = benchmark_opencv_method(video_path, ocr_engine)

        # Benchmark ffmpeg method
        ffmpeg_results = benchmark_ffmpeg_method(video_path, ocr_engine, temp_dir)

        # Compare results
        if opencv_results and ffmpeg_results:
            compare_methods(opencv_results, ffmpeg_results)
            save_comparison_results(opencv_results, ffmpeg_results, args.output)
        else:
            logger.error("One or both benchmarks failed")

    finally:
        # Cleanup
        if not args.keep_temp:
            cleanup_temp_files(temp_dir)
        else:
            logger.info("Temporary files kept at: %s", temp_dir)

    logger.info("Issue #173 decode comparison completed!")


if __name__ == "__main__":
    main()
