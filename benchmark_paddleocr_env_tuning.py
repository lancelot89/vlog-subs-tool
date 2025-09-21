#!/usr/bin/env python3
"""
Issue #174: PaddleOCR 並列化・MKLDNN有効化の環境変数チューニング

このスクリプトは、PaddleOCRの性能を最適化するための環境変数組み合わせを探索します:
- OMP_NUM_THREADS, MKL_NUM_THREADS (並列スレッド数)
- FLAGS_use_mkldnn (Intel MKL-DNN有効化)
- KMP_AFFINITY (スレッドアフィニティ)
- rec_batch_num (バッチサイズ)

最適な組み合わせを特定し、.env.example形式での推奨設定を提案します。
"""

import json
import logging
import multiprocessing
import os
import platform
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.core.extractor.ocr import OCRStageTimings, SimplePaddleOCREngine

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class EnvConfiguration:
    """Environment variable configuration for PaddleOCR optimization."""

    omp_threads: int
    mkl_threads: int
    mkldnn_enabled: bool = True
    kmp_affinity: Optional[str] = None
    rec_batch_num: int = 16

    def to_env_dict(self) -> Dict[str, str]:
        """Convert configuration to environment variable dictionary."""
        env_vars = {
            "OMP_NUM_THREADS": str(self.omp_threads),
            "MKL_NUM_THREADS": str(self.mkl_threads),
            "FLAGS_use_mkldnn": "1" if self.mkldnn_enabled else "0",
        }

        if self.kmp_affinity:
            env_vars["KMP_AFFINITY"] = self.kmp_affinity

        return env_vars

    def to_ocr_params(self) -> Dict[str, any]:
        """Convert configuration to PaddleOCR initialization parameters."""
        # Note: rec_batch_num is set via environment variable or PaddleOCR kwargs,
        # not SimplePaddleOCREngine constructor
        return {}

    def description(self) -> str:
        """Get human-readable description of the configuration."""
        parts = [
            f"OMP:{self.omp_threads}",
            f"MKL:{self.mkl_threads}",
            f"MKLDNN:{'ON' if self.mkldnn_enabled else 'OFF'}",
            f"batch:{self.rec_batch_num}",
        ]
        if self.kmp_affinity:
            parts.append(
                f"affinity:{self.kmp_affinity.split(',')[1] if ',' in self.kmp_affinity else 'custom'}"
            )
        return " | ".join(parts)


@dataclass
class BenchmarkResult:
    """Results from a single environment configuration benchmark."""

    config: EnvConfiguration
    total_time: float
    avg_ocr_time: float
    avg_detection_time: float
    avg_classification_time: float
    avg_recognition_time: float
    frames_processed: int
    improvement_vs_baseline: float = 0.0

    def to_dict(self) -> Dict:
        """Convert result to dictionary for JSON serialization."""
        return {
            "config": {
                "omp_threads": self.config.omp_threads,
                "mkl_threads": self.config.mkl_threads,
                "mkldnn_enabled": self.config.mkldnn_enabled,
                "kmp_affinity": self.config.kmp_affinity,
                "rec_batch_num": self.config.rec_batch_num,
                "description": self.config.description(),
            },
            "performance": {
                "total_time": self.total_time,
                "avg_ocr_time": self.avg_ocr_time,
                "avg_detection_time": self.avg_detection_time,
                "avg_classification_time": self.avg_classification_time,
                "avg_recognition_time": self.avg_recognition_time,
                "frames_processed": self.frames_processed,
                "improvement_vs_baseline": self.improvement_vs_baseline,
            },
        }


def get_physical_core_count() -> int:
    """Get the number of physical CPU cores."""
    try:
        return multiprocessing.cpu_count() // 2  # Assume hyperthreading
    except Exception:
        return 4  # Conservative fallback


def create_test_images(count: int = 10) -> List[np.ndarray]:
    """Create test images with Japanese text for benchmarking."""
    images = []
    width, height = 1280, 720

    # Japanese text samples for realistic OCR testing
    text_samples = [
        "こんにちは、世界！",
        "今日はいい天気ですね。",
        "PaddleOCRのテストです。",
        "環境変数の最適化を行います。",
        "性能改善を目指しています。",
        "日本語OCRの処理速度向上",
        "並列処理によるスピードアップ",
        "MKLDNN有効化の効果測定",
        "スレッド数の最適値を探索",
        "バッチサイズの調整テスト",
    ]

    for i in range(count):
        # Create white background
        image = np.ones((height, width, 3), dtype=np.uint8) * 255

        # Add Japanese subtitle text at bottom
        text = text_samples[i % len(text_samples)]
        # Use OpenCV's default font (doesn't support Japanese, but creates text regions for detection)
        cv2.putText(
            image,
            f"Frame {i+1}: {text}",
            (50, height - 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 0, 0),
            2,
        )

        # Add timestamp
        cv2.putText(
            image,
            f"Time: {i * 0.5:.1f}s",
            (50, height - 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (128, 128, 128),
            2,
        )

        images.append(image)

    return images


def apply_environment_config(config: EnvConfiguration) -> Dict[str, str]:
    """Apply environment configuration and return previous values for restoration."""
    env_vars = config.to_env_dict()
    previous_values = {}

    logger.info("Applying environment configuration: %s", config.description())

    for key, value in env_vars.items():
        previous_values[key] = os.environ.get(key)
        os.environ[key] = value
        logger.debug("Set %s=%s", key, value)

    return previous_values


def restore_environment(previous_values: Dict[str, Optional[str]]) -> None:
    """Restore previous environment variable values."""
    for key, value in previous_values.items():
        if value is None:
            if key in os.environ:
                del os.environ[key]
        else:
            os.environ[key] = value


def benchmark_configuration(
    config: EnvConfiguration, test_images: List[np.ndarray], runs: int = 3
) -> BenchmarkResult:
    """Benchmark a specific environment configuration."""
    logger.info("=" * 60)
    logger.info("BENCHMARKING: %s", config.description())
    logger.info("=" * 60)

    # Apply environment configuration
    previous_env = apply_environment_config(config)

    try:
        # Initialize OCR engine with standard configuration
        # Note: rec_batch_num and other PaddleOCR-specific parameters are controlled
        # via environment variables, not SimplePaddleOCREngine constructor
        ocr_engine = SimplePaddleOCREngine(
            language="ja",
            confidence_threshold=0.5,
            max_batch_size=1,
            max_image_pixels=2048 * 2048,
            max_side_length=2048,
        )

        if not ocr_engine.initialize():
            logger.error("Failed to initialize OCR engine with config: %s", config.description())
            return BenchmarkResult(
                config=config,
                total_time=float("inf"),
                avg_ocr_time=0,
                avg_detection_time=0,
                avg_classification_time=0,
                avg_recognition_time=0,
                frames_processed=0,
            )

        # Enable stage timing for detailed analysis
        ocr_engine.enable_stage_timing(True)

        # Run multiple benchmark runs for statistical accuracy
        run_results = []

        for run in range(runs):
            logger.info("Running benchmark %d/%d...", run + 1, runs)

            start_time = time.perf_counter()
            ocr_times = []
            detection_times = []
            classification_times = []
            recognition_times = []

            for i, image in enumerate(test_images):
                ocr_start = time.perf_counter()
                results = ocr_engine.extract_text(image)
                timing = ocr_engine.get_last_timing_results()
                ocr_time = time.perf_counter() - ocr_start

                ocr_times.append(ocr_time)

                if timing:
                    detection_times.append(timing.detection_time)
                    classification_times.append(timing.classification_time)
                    recognition_times.append(timing.recognition_time)

                if (i + 1) % 5 == 0:
                    logger.debug("Processed %d/%d images", i + 1, len(test_images))

            total_time = time.perf_counter() - start_time

            run_result = {
                "total_time": total_time,
                "avg_ocr_time": statistics.mean(ocr_times) if ocr_times else 0,
                "avg_detection_time": statistics.mean(detection_times) if detection_times else 0,
                "avg_classification_time": (
                    statistics.mean(classification_times) if classification_times else 0
                ),
                "avg_recognition_time": (
                    statistics.mean(recognition_times) if recognition_times else 0
                ),
                "frames_processed": len(test_images),
            }

            run_results.append(run_result)

            logger.info(
                "Run %d completed: %.3f s total, %.3f ms/frame",
                run + 1,
                total_time,
                run_result["avg_ocr_time"] * 1000,
            )

        # Calculate average across runs
        avg_result = BenchmarkResult(
            config=config,
            total_time=statistics.mean(r["total_time"] for r in run_results),
            avg_ocr_time=statistics.mean(r["avg_ocr_time"] for r in run_results),
            avg_detection_time=statistics.mean(r["avg_detection_time"] for r in run_results),
            avg_classification_time=statistics.mean(
                r["avg_classification_time"] for r in run_results
            ),
            avg_recognition_time=statistics.mean(r["avg_recognition_time"] for r in run_results),
            frames_processed=len(test_images),
        )

        logger.info(
            "AVERAGE RESULT: %.3f s total, %.3f ms/frame",
            avg_result.total_time,
            avg_result.avg_ocr_time * 1000,
        )

        return avg_result

    finally:
        # Always restore environment
        restore_environment(previous_env)


def generate_test_configurations(
    thread_counts: Optional[List[int]] = None,
    enable_mkldnn: bool = True,
    affinity_modes: Optional[List[str]] = None,
    auto_detect_cores: bool = False,
) -> List[EnvConfiguration]:
    """Generate test configurations for benchmarking."""
    if auto_detect_cores:
        physical_cores = get_physical_core_count()
        thread_counts = [1, 2, physical_cores // 2, physical_cores, physical_cores * 2]
        logger.info(
            "Auto-detected %d physical cores, testing thread counts: %s",
            physical_cores,
            thread_counts,
        )

    if thread_counts is None:
        thread_counts = [1, 2, 4, 8]

    if affinity_modes is None:
        affinity_modes = [None, "granularity=fine,compact,1,0", "granularity=fine,scatter,1,0"]

    configurations = []

    # Focus on environment variables optimization (Issue #174)
    # rec_batch_num testing can be added later as a separate feature
    rec_batch_num = 16  # Use default value

    for threads in thread_counts:
        for affinity in affinity_modes:
            config = EnvConfiguration(
                omp_threads=threads,
                mkl_threads=threads,
                mkldnn_enabled=enable_mkldnn,
                kmp_affinity=affinity,
                rec_batch_num=rec_batch_num,
            )
            configurations.append(config)

    logger.info("Generated %d test configurations", len(configurations))
    return configurations


def analyze_results(results: List[BenchmarkResult]) -> Tuple[BenchmarkResult, Dict]:
    """Analyze benchmark results and find the best configuration."""
    if not results:
        raise ValueError("No results to analyze")

    # Find baseline (first result or a specific baseline configuration)
    baseline = results[0]
    for result in results:
        if result.config.omp_threads == 1 and not result.config.mkldnn_enabled:
            baseline = result
            break

    # Calculate improvements vs baseline
    for result in results:
        if baseline.total_time > 0:
            result.improvement_vs_baseline = (
                (baseline.total_time - result.total_time) / baseline.total_time
            ) * 100

    # Sort by performance (lowest total time = best)
    sorted_results = sorted(results, key=lambda r: r.total_time)
    best_result = sorted_results[0]

    # Analysis summary
    analysis = {
        "best_config": best_result.config.description(),
        "best_total_time": best_result.total_time,
        "baseline_total_time": baseline.total_time,
        "improvement_vs_baseline": best_result.improvement_vs_baseline,
        "avg_ocr_time_improvement": (
            ((baseline.avg_ocr_time - best_result.avg_ocr_time) / baseline.avg_ocr_time * 100)
            if baseline.avg_ocr_time > 0
            else 0
        ),
        "top_3_configs": [
            {
                "config": r.config.description(),
                "total_time": r.total_time,
                "improvement": r.improvement_vs_baseline,
            }
            for r in sorted_results[:3]
        ],
    }

    return best_result, analysis


def generate_env_config_file(best_result: BenchmarkResult, output_path: Path) -> None:
    """Generate .env.example file with optimal settings."""
    env_vars = best_result.config.to_env_dict()
    ocr_params = best_result.config.to_ocr_params()

    env_content = f"""# PaddleOCR Environment Variable Optimization (Issue #174)
# Automatically generated optimal configuration
# Platform: {platform.system()} {platform.machine()}
# Performance improvement: {best_result.improvement_vs_baseline:.1f}%

# OpenMP parallel threads (CPU cores)
OMP_NUM_THREADS={env_vars.get('OMP_NUM_THREADS', '4')}

# Intel MKL parallel threads
MKL_NUM_THREADS={env_vars.get('MKL_NUM_THREADS', '4')}

# Enable Intel MKL-DNN optimization
FLAGS_use_mkldnn={env_vars.get('FLAGS_use_mkldnn', '1')}

# Thread affinity (optional - uncomment if beneficial)
"""

    if best_result.config.kmp_affinity:
        env_content += f"KMP_AFFINITY={best_result.config.kmp_affinity}\n"
    else:
        env_content += "# KMP_AFFINITY=granularity=fine,compact,1,0\n"

    env_content += f"""
# PaddleOCR Parameters
# rec_batch_num optimization requires separate investigation
# Current focus: Environment variable optimization (Issue #174)

# Performance Results:
# - Total processing time: {best_result.total_time:.3f} seconds
# - Average OCR time per frame: {best_result.avg_ocr_time * 1000:.3f} ms
# - Frames processed: {best_result.frames_processed}
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    logger.info("Optimal environment configuration saved to: %s", output_path)


def save_detailed_results(
    results: List[BenchmarkResult], analysis: Dict, output_file: Path
) -> None:
    """Save detailed benchmark results to JSON file."""
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": f"{platform.system()}/{platform.machine()}",
        "physical_cores": get_physical_core_count(),
        "analysis": analysis,
        "results": [result.to_dict() for result in results],
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logger.info("Detailed results saved to: %s", output_file)


def print_results_summary(results: List[BenchmarkResult], analysis: Dict) -> None:
    """Print comprehensive results summary."""
    logger.info("=" * 80)
    logger.info("PADDLEOCR ENVIRONMENT VARIABLE TUNING RESULTS")
    logger.info("=" * 80)

    logger.info("PLATFORM INFO:")
    logger.info("  System: %s %s", platform.system(), platform.machine())
    logger.info("  Physical cores: %d", get_physical_core_count())
    logger.info("  Configurations tested: %d", len(results))

    logger.info("=" * 80)
    logger.info("PERFORMANCE ANALYSIS:")
    logger.info("  Best configuration: %s", analysis["best_config"])
    logger.info("  Best total time: %.3f s", analysis["best_total_time"])
    logger.info("  Baseline total time: %.3f s", analysis["baseline_total_time"])
    logger.info("  Overall improvement: %+.1f%%", analysis["improvement_vs_baseline"])
    logger.info("  OCR time improvement: %+.1f%%", analysis["avg_ocr_time_improvement"])

    logger.info("=" * 80)
    logger.info("TOP 3 CONFIGURATIONS:")
    for i, config_info in enumerate(analysis["top_3_configs"], 1):
        logger.info("  %d. %s", i, config_info["config"])
        logger.info(
            "     Total time: %.3f s | Improvement: %+.1f%%",
            config_info["total_time"],
            config_info["improvement"],
        )

    logger.info("=" * 80)
    logger.info("ISSUE #174 RECOMMENDATIONS:")

    improvement = analysis["improvement_vs_baseline"]
    if improvement > 30:
        logger.info("🚀 Significant improvement (%.1f%%)", improvement)
        logger.info("   RECOMMEND: Apply optimal settings as default configuration")
        logger.info("   BENEFIT: Major performance boost for CPU-based OCR processing")
    elif improvement > 10:
        logger.info("✅ Moderate improvement (%.1f%%)", improvement)
        logger.info("   RECOMMEND: Provide optimal settings as configuration option")
        logger.info("   BENEFIT: Meaningful performance enhancement")
    elif improvement > 0:
        logger.info("📊 Minor improvement (%.1f%%)", improvement)
        logger.info("   CONSIDER: Optional optimization for performance-critical scenarios")
    else:
        logger.info("⚖️  No significant improvement (%.1f%%)", improvement)
        logger.info("   RECOMMEND: Keep current default settings")
        logger.info("   BENEFIT: Simplicity over marginal gains")

    logger.info("=" * 80)


def main() -> None:
    """Main function to run PaddleOCR environment variable tuning."""
    import argparse

    parser = argparse.ArgumentParser(description="PaddleOCR environment variable tuning benchmark")
    parser.add_argument(
        "--thread-counts",
        type=str,
        default="1,2,4,8",
        help="Comma-separated list of thread counts to test",
    )
    # Note: rec-batch-sizes parameter removed for Issue #174 focus on environment variables
    # Can be re-added later for comprehensive PaddleOCR parameter optimization
    parser.add_argument(
        "--affinity-modes",
        type=str,
        default="none,compact,scatter",
        help="Comma-separated list of affinity modes (none,compact,scatter)",
    )
    parser.add_argument(
        "--mkldnn-enabled",
        action="store_true",
        default=True,
        help="Enable Intel MKL-DNN optimization",
    )
    parser.add_argument(
        "--auto-detect-cores",
        action="store_true",
        help="Auto-detect physical core count and generate thread counts",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of benchmark runs per configuration",
    )
    parser.add_argument(
        "--test-images",
        type=int,
        default=10,
        help="Number of test images to process",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for detailed results",
    )
    parser.add_argument(
        "--generate-env-config",
        action="store_true",
        help="Generate .env.example file with optimal settings",
    )
    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help="Run comprehensive test with all combinations",
    )

    args = parser.parse_args()

    # Set default output filename
    if args.output is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        args.output = Path(f"paddleocr_env_tuning_{timestamp}.json")

    # Parse arguments
    thread_counts = [int(x.strip()) for x in args.thread_counts.split(",")]

    affinity_mapping = {
        "none": None,
        "compact": "granularity=fine,compact,1,0",
        "scatter": "granularity=fine,scatter,1,0",
    }
    affinity_modes = [affinity_mapping.get(mode.strip()) for mode in args.affinity_modes.split(",")]

    if args.comprehensive:
        # Use all available options for comprehensive testing
        thread_counts = [1, 2, 4, 8, 16]
        affinity_modes = list(affinity_mapping.values())

    logger.info("=" * 80)
    logger.info("Issue #174: PaddleOCR Environment Variable Tuning")
    logger.info("Platform: %s %s", platform.system(), platform.machine())
    logger.info("Physical cores: %d", get_physical_core_count())
    logger.info("=" * 80)

    # Create test images
    logger.info("Creating %d test images...", args.test_images)
    test_images = create_test_images(args.test_images)

    # Generate test configurations
    configurations = generate_test_configurations(
        thread_counts=thread_counts,
        enable_mkldnn=args.mkldnn_enabled,
        affinity_modes=affinity_modes,
        auto_detect_cores=args.auto_detect_cores,
    )

    # Run benchmarks
    logger.info("Starting environment variable tuning benchmarks...")
    results = []

    for i, config in enumerate(configurations):
        logger.info("Configuration %d/%d: %s", i + 1, len(configurations), config.description())
        try:
            result = benchmark_configuration(config, test_images, args.runs)
            results.append(result)
        except Exception as e:
            logger.error("Failed to benchmark configuration %s: %s", config.description(), e)
            continue

    if not results:
        logger.error("No successful benchmark results")
        return

    # Analyze results
    best_result, analysis = analyze_results(results)

    # Print summary
    print_results_summary(results, analysis)

    # Save detailed results
    save_detailed_results(results, analysis, args.output)

    # Generate environment configuration file
    if args.generate_env_config:
        env_config_path = args.output.parent / "optimal_env_config.env"
        generate_env_config_file(best_result, env_config_path)

    logger.info("Issue #174 PaddleOCR environment tuning completed!")


if __name__ == "__main__":
    main()
