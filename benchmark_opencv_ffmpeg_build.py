#!/usr/bin/env python3
"""
Issue #175: OpenCV/FFmpeg ビルド差の確認と採用方針の決定

このスクリプトは、OpenCVビルド構成とFFmpegバージョンの性能差を調査します:
- opencv-python vs opencv-python-headless
- 同梱FFmpeg vs 外部FFmpeg
- バージョン差による動画処理性能への影響

最適なビルド構成と依存関係固定方針を技術的に決定します。
"""

import json
import logging
import platform
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class OpenCVBuildInfo:
    """OpenCV build configuration information."""

    version: str
    build_info: str
    gui_support: bool
    ffmpeg_enabled: bool
    package_name: str  # opencv-python or opencv-python-headless
    ffmpeg_version: Optional[str] = None

    def description(self) -> str:
        """Get human-readable description of the OpenCV build."""
        return f"{self.package_name} {self.version} (GUI:{self.gui_support}, FFmpeg:{self.ffmpeg_enabled})"


@dataclass
class FFmpegInfo:
    """FFmpeg version and configuration information."""

    version: str
    source: str  # "opencv-bundled", "system", "external"
    build_config: str
    codecs_supported: List[str]

    def description(self) -> str:
        """Get human-readable description of FFmpeg."""
        return f"FFmpeg {self.version} ({self.source}) - {len(self.codecs_supported)} codecs"


@dataclass
class PerformanceResult:
    """Performance measurement results."""

    test_name: str
    opencv_build: OpenCVBuildInfo
    ffmpeg_info: FFmpegInfo
    video_read_time: float
    video_write_time: float
    decode_fps: float
    encode_fps: float
    memory_usage_mb: float
    cpu_usage_percent: float

    def to_dict(self) -> Dict:
        """Convert result to dictionary for JSON serialization."""
        return {
            "test_name": self.test_name,
            "opencv_build": {
                "version": self.opencv_build.version,
                "package_name": self.opencv_build.package_name,
                "gui_support": self.opencv_build.gui_support,
                "ffmpeg_enabled": self.opencv_build.ffmpeg_enabled,
                "description": self.opencv_build.description(),
            },
            "ffmpeg_info": {
                "version": self.ffmpeg_info.version,
                "source": self.ffmpeg_info.source,
                "codecs_count": len(self.ffmpeg_info.codecs_supported),
                "description": self.ffmpeg_info.description(),
            },
            "performance": {
                "video_read_time": self.video_read_time,
                "video_write_time": self.video_write_time,
                "decode_fps": self.decode_fps,
                "encode_fps": self.encode_fps,
                "memory_usage_mb": self.memory_usage_mb,
                "cpu_usage_percent": self.cpu_usage_percent,
            },
        }


def get_opencv_build_info() -> OpenCVBuildInfo:
    """Get current OpenCV build information."""
    version = cv2.__version__
    build_info = cv2.getBuildInformation()

    # Check GUI support
    gui_support = hasattr(cv2, "imshow") and hasattr(cv2, "waitKey")

    # Check FFmpeg support
    ffmpeg_enabled = False
    try:
        # Try to create a VideoCapture instance to test FFmpeg
        cap = cv2.VideoCapture()
        ffmpeg_enabled = True
        cap.release()
    except Exception:
        pass

    # Determine package name from build info
    package_name = "opencv-python-headless"
    if gui_support:
        package_name = "opencv-python"

    # Extract FFmpeg version from build info
    ffmpeg_version = None
    ffmpeg_match = re.search(r"FFmpeg\s*:\s*YES\s*\(([^)]+)\)", build_info)
    if ffmpeg_match:
        ffmpeg_version = ffmpeg_match.group(1).strip()

    return OpenCVBuildInfo(
        version=version,
        build_info=build_info,
        gui_support=gui_support,
        ffmpeg_enabled=ffmpeg_enabled,
        package_name=package_name,
        ffmpeg_version=ffmpeg_version,
    )


def get_ffmpeg_info() -> FFmpegInfo:
    """Get FFmpeg information."""
    # Try to get system FFmpeg version
    system_ffmpeg_version = None
    system_ffmpeg_config = ""

    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.split("\n")
            if lines:
                version_line = lines[0]
                version_match = re.search(r"ffmpeg version ([^\s]+)", version_line)
                if version_match:
                    system_ffmpeg_version = version_match.group(1)
                system_ffmpeg_config = result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Get OpenCV's FFmpeg information
    opencv_build = get_opencv_build_info()

    if system_ffmpeg_version:
        return FFmpegInfo(
            version=system_ffmpeg_version,
            source="system",
            build_config=system_ffmpeg_config,
            codecs_supported=extract_supported_codecs(system_ffmpeg_config),
        )
    elif opencv_build.ffmpeg_version:
        return FFmpegInfo(
            version=opencv_build.ffmpeg_version,
            source="opencv-bundled",
            build_config=opencv_build.build_info,
            codecs_supported=extract_opencv_codecs(opencv_build.build_info),
        )
    else:
        return FFmpegInfo(
            version="unknown",
            source="none",
            build_config="",
            codecs_supported=[],
        )


def extract_supported_codecs(ffmpeg_output: str) -> List[str]:
    """Extract supported codecs from FFmpeg output."""
    codecs = []

    # Look for common codec indicators
    codec_patterns = [
        r"--enable-([a-zA-Z0-9_-]+)",
        r"lib([a-zA-Z0-9_-]+)\s+\[",
    ]

    for pattern in codec_patterns:
        matches = re.findall(pattern, ffmpeg_output)
        codecs.extend(matches)

    # Add common codecs we know about
    common_codecs = ["h264", "hevc", "vp8", "vp9", "av1", "mp4", "avi", "mov"]
    for codec in common_codecs:
        if codec.lower() in ffmpeg_output.lower() and codec not in codecs:
            codecs.append(codec)

    return sorted(list(set(codecs)))


def extract_opencv_codecs(build_info: str) -> List[str]:
    """Extract supported codecs from OpenCV build information."""
    codecs = []

    # Look for media I/O libraries in build info
    if "FFmpeg" in build_info:
        codecs.extend(["h264", "hevc", "mp4", "avi", "mov"])
    if "GStreamer" in build_info:
        codecs.extend(["gstreamer"])
    if "DirectShow" in build_info:
        codecs.extend(["directshow"])

    return sorted(list(set(codecs)))


def create_test_video(
    output_path: Path, duration: int = 5, fps: int = 30, resolution: Tuple[int, int] = (1280, 720)
) -> bool:
    """Create a test video for benchmarking."""
    try:
        width, height = resolution
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
        if not writer.isOpened():
            logger.error("Failed to open VideoWriter")
            return False

        total_frames = duration * fps
        logger.info(
            "Creating test video: %d frames at %d fps (%dx%d)", total_frames, fps, width, height
        )

        for frame_num in range(total_frames):
            # Create gradient background
            frame = np.zeros((height, width, 3), dtype=np.uint8)

            # Add animated gradient
            gradient_shift = (frame_num * 2) % 255
            for y in range(height):
                color_value = (y + gradient_shift) % 255
                frame[y, :, 0] = color_value  # Blue channel
                frame[y, :, 1] = (color_value + 85) % 255  # Green channel
                frame[y, :, 2] = (color_value + 170) % 255  # Red channel

            # Add moving text
            text = f"OpenCV Build Test Frame {frame_num + 1}"
            x_pos = (frame_num * 5) % (width - 300)
            cv2.putText(
                frame,
                text,
                (x_pos, height // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 255),
                2,
            )

            # Add timestamp
            timestamp = f"Time: {frame_num / fps:.2f}s"
            cv2.putText(
                frame,
                timestamp,
                (50, height - 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (200, 200, 200),
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


def benchmark_video_reading(video_path: Path, runs: int = 3) -> Tuple[float, float]:
    """Benchmark video reading performance."""
    logger.info("Benchmarking video reading: %s", video_path)

    read_times = []
    frame_counts = []

    for run in range(runs):
        start_time = time.perf_counter()

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.error("Failed to open video: %s", video_path)
            return 0.0, 0.0

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1

        cap.release()
        read_time = time.perf_counter() - start_time

        read_times.append(read_time)
        frame_counts.append(frame_count)

        logger.debug("Run %d: read %d frames in %.3f seconds", run + 1, frame_count, read_time)

    avg_read_time = sum(read_times) / len(read_times)
    avg_frame_count = sum(frame_counts) / len(frame_counts)
    avg_fps = avg_frame_count / avg_read_time if avg_read_time > 0 else 0

    logger.info("Average reading: %.3f seconds, %.1f fps", avg_read_time, avg_fps)
    return avg_read_time, avg_fps


def benchmark_video_writing(
    temp_dir: Path, duration: int = 3, fps: int = 30, runs: int = 3
) -> Tuple[float, float]:
    """Benchmark video writing performance."""
    logger.info("Benchmarking video writing")

    write_times = []
    frame_counts = []

    for run in range(runs):
        output_path = temp_dir / f"write_test_{run}.mp4"

        start_time = time.perf_counter()

        # Create and write test video
        if create_test_video(output_path, duration, fps):
            write_time = time.perf_counter() - start_time
            frame_count = duration * fps

            write_times.append(write_time)
            frame_counts.append(frame_count)

            logger.debug(
                "Run %d: wrote %d frames in %.3f seconds", run + 1, frame_count, write_time
            )

            # Clean up
            if output_path.exists():
                output_path.unlink()
        else:
            logger.warning("Failed to create test video for run %d", run + 1)

    if not write_times:
        return 0.0, 0.0

    avg_write_time = sum(write_times) / len(write_times)
    avg_frame_count = sum(frame_counts) / len(frame_counts)
    avg_fps = avg_frame_count / avg_write_time if avg_write_time > 0 else 0

    logger.info("Average writing: %.3f seconds, %.1f fps", avg_write_time, avg_fps)
    return avg_write_time, avg_fps


def estimate_memory_usage() -> float:
    """Estimate current memory usage in MB."""
    try:
        import psutil

        process = psutil.Process()
        memory_info = process.memory_info()
        return memory_info.rss / 1024 / 1024  # Convert to MB
    except ImportError:
        logger.warning("psutil not available for memory measurement")
        return 0.0


def estimate_cpu_usage() -> float:
    """Estimate current CPU usage percentage."""
    try:
        import psutil

        return psutil.cpu_percent(interval=1)
    except ImportError:
        logger.warning("psutil not available for CPU measurement")
        return 0.0


def run_performance_benchmark(
    test_name: str, test_video_path: Optional[Path] = None
) -> PerformanceResult:
    """Run comprehensive performance benchmark."""
    logger.info("Running performance benchmark: %s", test_name)

    # Get build information
    opencv_build = get_opencv_build_info()
    ffmpeg_info = get_ffmpeg_info()

    logger.info("OpenCV Build: %s", opencv_build.description())
    logger.info("FFmpeg Info: %s", ffmpeg_info.description())

    # Create temporary directory for testing
    with tempfile.TemporaryDirectory(prefix="opencv_benchmark_") as temp_dir:
        temp_path = Path(temp_dir)

        # Use provided test video or create one
        if test_video_path and test_video_path.exists():
            video_path = test_video_path
            logger.info("Using provided test video: %s", video_path)
        else:
            video_path = temp_path / "benchmark_test.mp4"
            logger.info("Creating test video: %s", video_path)
            if not create_test_video(video_path, duration=5, fps=30):
                raise RuntimeError("Failed to create test video")

        # Measure system resources before testing
        initial_memory = estimate_memory_usage()

        # Benchmark video reading
        read_time, decode_fps = benchmark_video_reading(video_path)

        # Benchmark video writing
        write_time, encode_fps = benchmark_video_writing(temp_path)

        # Measure system resources after testing
        final_memory = estimate_memory_usage()
        cpu_usage = estimate_cpu_usage()

        memory_usage = max(0.0, final_memory - initial_memory)

    return PerformanceResult(
        test_name=test_name,
        opencv_build=opencv_build,
        ffmpeg_info=ffmpeg_info,
        video_read_time=read_time,
        video_write_time=write_time,
        decode_fps=decode_fps,
        encode_fps=encode_fps,
        memory_usage_mb=memory_usage,
        cpu_usage_percent=cpu_usage,
    )


def compare_results(results: List[PerformanceResult]) -> Dict:
    """Compare benchmark results and generate analysis."""
    if not results:
        raise ValueError("No results to compare")

    # Find baseline (first result or opencv-python-headless if available)
    baseline = results[0]
    for result in results:
        if "headless" in result.opencv_build.package_name.lower():
            baseline = result
            break

    analysis = {
        "baseline": {
            "test_name": baseline.test_name,
            "opencv_build": baseline.opencv_build.description(),
            "decode_fps": baseline.decode_fps,
            "encode_fps": baseline.encode_fps,
        },
        "comparisons": [],
        "recommendations": {},
    }

    for result in results:
        if result == baseline:
            continue

        # Calculate improvements
        decode_improvement = (
            ((result.decode_fps - baseline.decode_fps) / baseline.decode_fps * 100)
            if baseline.decode_fps > 0
            else 0
        )
        encode_improvement = (
            ((result.encode_fps - baseline.encode_fps) / baseline.encode_fps * 100)
            if baseline.encode_fps > 0
            else 0
        )
        memory_diff = result.memory_usage_mb - baseline.memory_usage_mb

        comparison = {
            "test_name": result.test_name,
            "opencv_build": result.opencv_build.description(),
            "decode_fps": result.decode_fps,
            "encode_fps": result.encode_fps,
            "decode_improvement": decode_improvement,
            "encode_improvement": encode_improvement,
            "memory_difference_mb": memory_diff,
        }

        analysis["comparisons"].append(comparison)

    # Generate recommendations
    if analysis["comparisons"]:
        best_decode = max(results, key=lambda r: r.decode_fps)
        best_encode = max(results, key=lambda r: r.encode_fps)

        analysis["recommendations"] = {
            "best_decode_performance": {
                "test_name": best_decode.test_name,
                "opencv_build": best_decode.opencv_build.description(),
                "decode_fps": best_decode.decode_fps,
            },
            "best_encode_performance": {
                "test_name": best_encode.test_name,
                "opencv_build": best_encode.opencv_build.description(),
                "encode_fps": best_encode.encode_fps,
            },
        }

    return analysis


def print_results_summary(results: List[PerformanceResult], analysis: Dict) -> None:
    """Print comprehensive results summary."""
    logger.info("=" * 80)
    logger.info("OPENCV/FFMPEG BUILD COMPARISON RESULTS")
    logger.info("=" * 80)

    logger.info("PLATFORM INFO:")
    logger.info("  System: %s %s", platform.system(), platform.machine())
    logger.info("  Tests run: %d", len(results))

    logger.info("=" * 80)
    logger.info("PERFORMANCE COMPARISON:")

    baseline_info = analysis.get("baseline", {})
    logger.info("BASELINE: %s", baseline_info.get("test_name", "Unknown"))
    logger.info("  OpenCV: %s", baseline_info.get("opencv_build", "Unknown"))
    logger.info("  Decode: %.1f fps", baseline_info.get("decode_fps", 0))
    logger.info("  Encode: %.1f fps", baseline_info.get("encode_fps", 0))

    for comparison in analysis.get("comparisons", []):
        logger.info("COMPARISON: %s", comparison["test_name"])
        logger.info("  OpenCV: %s", comparison["opencv_build"])
        logger.info(
            "  Decode: %.1f fps (%+.1f%%)",
            comparison["decode_fps"],
            comparison["decode_improvement"],
        )
        logger.info(
            "  Encode: %.1f fps (%+.1f%%)",
            comparison["encode_fps"],
            comparison["encode_improvement"],
        )
        logger.info("  Memory: %+.1f MB", comparison["memory_difference_mb"])

    logger.info("=" * 80)
    logger.info("ISSUE #175 RECOMMENDATIONS:")

    recommendations = analysis.get("recommendations", {})
    if recommendations:
        best_decode = recommendations.get("best_decode_performance", {})
        best_encode = recommendations.get("best_encode_performance", {})

        logger.info("🚀 Best Decode Performance: %s", best_decode.get("test_name", "Unknown"))
        logger.info("   Build: %s", best_decode.get("opencv_build", "Unknown"))
        logger.info("   Performance: %.1f fps", best_decode.get("decode_fps", 0))

        logger.info("📹 Best Encode Performance: %s", best_encode.get("test_name", "Unknown"))
        logger.info("   Build: %s", best_encode.get("opencv_build", "Unknown"))
        logger.info("   Performance: %.1f fps", best_encode.get("encode_fps", 0))

        # Determine overall recommendation
        overall_improvements = [
            comp["decode_improvement"] + comp["encode_improvement"]
            for comp in analysis.get("comparisons", [])
        ]
        if overall_improvements:
            max_improvement = max(overall_improvements)
            if max_improvement > 20:
                logger.info("✅ RECOMMEND: Use highest performing build as default")
                logger.info(
                    "   BENEFIT: Significant performance improvement (%.1f%%)", max_improvement
                )
            elif max_improvement > 5:
                logger.info("📊 CONSIDER: Provide build options for different use cases")
                logger.info(
                    "   BENEFIT: Moderate performance improvement (%.1f%%)", max_improvement
                )
            else:
                logger.info("⚖️ RECOMMEND: Maintain current build for stability")
                logger.info("   BENEFIT: Minimal performance difference, prioritize compatibility")

    logger.info("=" * 80)


def generate_requirements_file(
    results: List[PerformanceResult], output_path: Path, format_type: str = "requirements.txt"
) -> None:
    """Generate requirements file with optimal OpenCV version."""
    if not results:
        logger.warning("No results to generate requirements from")
        return

    # Find the best performing configuration
    best_result = max(results, key=lambda r: r.decode_fps + r.encode_fps)

    if format_type == "requirements.txt":
        content = f"""# OpenCV Build Optimization (Issue #175)
# Generated based on performance benchmark results
# Best configuration: {best_result.opencv_build.description()}

# OpenCV package (choose one based on needs)
"""
        if "headless" in best_result.opencv_build.package_name.lower():
            content += (
                f"{best_result.opencv_build.package_name}=={best_result.opencv_build.version}\n"
            )
            content += f"# Alternative: opencv-python=={best_result.opencv_build.version}  # if GUI needed\n"
        else:
            content += (
                f"{best_result.opencv_build.package_name}=={best_result.opencv_build.version}\n"
            )
            content += f"# Alternative: opencv-python-headless=={best_result.opencv_build.version}  # if no GUI needed\n"

        content += f"""
# Performance Results:
# - Decode FPS: {best_result.decode_fps:.1f}
# - Encode FPS: {best_result.encode_fps:.1f}
# - Memory usage: {best_result.memory_usage_mb:.1f} MB

# Other dependencies
numpy>=1.21.0
"""

    elif format_type == "poetry":
        content = f"""# Add to pyproject.toml [tool.poetry.dependencies]
# OpenCV Build Optimization (Issue #175)

# Best performing configuration: {best_result.opencv_build.description()}
{best_result.opencv_build.package_name} = "=={best_result.opencv_build.version}"

# Performance: Decode {best_result.decode_fps:.1f}fps, Encode {best_result.encode_fps:.1f}fps
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Requirements file generated: %s", output_path)


def save_detailed_results(
    results: List[PerformanceResult], analysis: Dict, output_file: Path
) -> None:
    """Save detailed benchmark results to JSON file."""
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": f"{platform.system()}/{platform.machine()}",
        "analysis": analysis,
        "results": [result.to_dict() for result in results],
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logger.info("Detailed results saved to: %s", output_file)


def main() -> None:
    """Main function to run OpenCV/FFmpeg build comparison."""
    import argparse

    parser = argparse.ArgumentParser(description="OpenCV/FFmpeg build comparison benchmark")
    parser.add_argument(
        "--test-video",
        type=Path,
        default=None,
        help="Path to test video file (will create one if not provided)",
    )
    parser.add_argument(
        "--current-config",
        action="store_true",
        help="Test current OpenCV configuration",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Mark this test as baseline for comparison",
    )
    parser.add_argument(
        "--test-name",
        type=str,
        default="opencv-build-test",
        help="Name for this test configuration",
    )
    parser.add_argument(
        "--ffmpeg-analysis",
        action="store_true",
        help="Include detailed FFmpeg analysis",
    )
    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help="Run comprehensive build comparison",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for detailed results",
    )
    parser.add_argument(
        "--generate-requirements",
        action="store_true",
        help="Generate optimized requirements.txt file",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["requirements.txt", "poetry"],
        default="requirements.txt",
        help="Format for requirements file",
    )

    args = parser.parse_args()

    # Set default output filename
    if args.output is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        args.output = Path(f"opencv_build_comparison_{timestamp}.json")

    logger.info("=" * 80)
    logger.info("Issue #175: OpenCV/FFmpeg Build Comparison")
    logger.info("Platform: %s %s", platform.system(), platform.machine())
    logger.info("=" * 80)

    # Run benchmarks
    results = []

    if args.current_config or not args.comprehensive:
        # Test current configuration
        test_name = args.test_name
        if args.baseline:
            test_name += "-baseline"

        logger.info("Testing current OpenCV configuration...")
        result = run_performance_benchmark(test_name, args.test_video)
        results.append(result)

    if args.comprehensive:
        # This would require multiple environments to test different OpenCV builds
        # For now, just test the current configuration with detailed analysis
        logger.info("Running comprehensive analysis of current build...")

        current_result = run_performance_benchmark("current-build", args.test_video)
        results.append(current_result)

        # Add FFmpeg analysis if requested
        if args.ffmpeg_analysis:
            logger.info("Analyzing FFmpeg configuration...")
            # Additional FFmpeg-specific tests could be added here

    if not results:
        logger.error("No benchmark results to analyze")
        return

    # Analyze results
    analysis = compare_results(results)

    # Print summary
    print_results_summary(results, analysis)

    # Save detailed results
    save_detailed_results(results, analysis, args.output)

    # Generate requirements file if requested
    if args.generate_requirements:
        req_file = args.output.parent / f"optimal_opencv_requirements.{args.format.split('.')[0]}"
        generate_requirements_file(results, req_file, args.format)

    logger.info("Issue #175 OpenCV/FFmpeg build comparison completed!")


if __name__ == "__main__":
    main()
