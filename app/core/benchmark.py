"""OCRベンチマーク・診断システム.

このモジュールは各プラットフォーム環境でのOCR性能を定量測定し、
問題の早期発見と最適化効果の可視化を実現します。
"""

from __future__ import annotations

import json
import logging
import os
import platform
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False
import statistics
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """ベンチマーク実行結果."""

    platform: str                           # プラットフォーム名
    cpu_info: str                          # CPU情報
    processing_time: Dict[str, float]      # 画像別処理時間（秒）
    accuracy_score: Dict[str, float]       # 認識精度スコア（0-1）
    memory_usage: float                    # 最大メモリ使用量（MB）
    thread_config: Dict[str, Any]         # 使用したスレッド設定
    ocr_settings: Dict[str, Any]          # OCR設定
    timestamp: str                         # 実行日時
    errors: Dict[str, str]                 # エラー情報（画像別）

    def overall_performance_score(self) -> float:
        """総合性能スコア（0-100）を計算."""
        if not self.processing_time:
            return 0.0

        # 処理速度スコア（逆数で高速ほど高得点）
        avg_time = statistics.mean(self.processing_time.values())
        speed_score = min(100, 10 / avg_time) if avg_time > 0 else 0

        # 精度スコア
        avg_accuracy = statistics.mean(self.accuracy_score.values()) if self.accuracy_score else 0
        accuracy_score = avg_accuracy * 100

        # 総合スコア（速度50%、精度50%）
        return (speed_score * 0.5 + accuracy_score * 0.5)

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換."""
        return asdict(self)


@dataclass
class Issue:
    """性能問題の診断結果."""

    severity: str                    # Critical, High, Medium, Low
    description: str                 # 問題の説明
    recommendation: str              # 推奨対処法
    estimated_improvement: str       # 期待される改善効果


@dataclass
class ComparisonReport:
    """プラットフォーム間比較レポート."""

    overall_performance_ratio: float          # 総合性能比率（1.0=基準値）
    detailed_comparison: Dict[str, float]     # 詳細比較（画像別性能比率）
    recommendations: List[str]                # 推奨事項
    estimated_improvement: str                # 期待される改善効果


class BenchmarkImageSet:
    """OCR性能測定用の標準画像セット."""

    def __init__(self, base_dir: Optional[Path] = None):
        """初期化.

        Args:
            base_dir: ベンチマーク画像ディレクトリのパス
        """
        if base_dir is None:
            # プロジェクトルートからの相対パス
            base_dir = Path(__file__).parent.parent.parent / "benchmark_images"

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)

        # 標準テスト画像の定義
        self.images = {
            "small_text": "sample_small_subtitle.png",      # 1行、20文字程度
            "large_text": "sample_large_subtitle.png",      # 2行、42文字程度
            "complex_scene": "sample_complex_scene.png",    # 背景複雑
            "high_res": "sample_4k_subtitle.png",           # 4K解像度
            "multi_language": "sample_mixed_lang.png",      # 日英混在
        }

        # 期待される認識結果
        self.expected_results = {
            "small_text": "こんにちは",
            "large_text": "字幕OCR翻訳アプリケーション\nテスト用サンプル画像",
            "complex_scene": "複雑な背景での認識テスト",
            "high_res": "高解像度4K画像テスト",
            "multi_language": "Hello こんにちは World",
        }

    def get_image_path(self, image_key: str) -> Path:
        """画像ファイルのパスを取得."""
        if image_key not in self.images:
            raise ValueError(f"Unknown image key: {image_key}")
        return self.base_dir / self.images[image_key]

    def get_expected_result(self, image_key: str) -> str:
        """期待される認識結果を取得."""
        return self.expected_results.get(image_key, "")

    def list_available_images(self) -> List[str]:
        """利用可能な画像キーのリストを取得."""
        return list(self.images.keys())

    def verify_images_exist(self) -> Dict[str, bool]:
        """テスト画像ファイルの存在確認."""
        results = {}
        for key, filename in self.images.items():
            image_path = self.base_dir / filename
            results[key] = image_path.exists()
        return results

    def create_sample_images(self) -> None:
        """サンプル画像を生成（テスト用）."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            # フォントパスの検出
            font_paths = [
                "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",  # macOS
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",   # Linux
                "C:\\Windows\\Fonts\\msgothic.ttc",                   # Windows
            ]

            font_path = None
            for path in font_paths:
                if Path(path).exists():
                    font_path = path
                    break

            # 各テスト画像を生成
            self._create_small_text_image(font_path)
            self._create_large_text_image(font_path)
            self._create_complex_scene_image(font_path)
            self._create_high_res_image(font_path)
            self._create_multi_language_image(font_path)

            logger.info("サンプルベンチマーク画像を生成しました: %s", self.base_dir)

        except ImportError as e:
            logger.warning("画像生成に必要なライブラリがインストールされていません: %s", e)
            logger.info("実際のテスト画像を %s に配置してください", self.base_dir)
            # 代わりに空の画像ファイルを作成（テスト用）
            self._create_dummy_images()

    def _create_small_text_image(self, font_path: Optional[str]) -> None:
        """小さなテキスト画像を生成."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            img = Image.new('RGB', (400, 100), color='black')
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype(font_path, 24) if font_path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            draw.text((50, 35), self.expected_results["small_text"], fill='white', font=font)
            img.save(self.base_dir / self.images["small_text"])

        except Exception as e:
            logger.warning("小テキスト画像の生成に失敗: %s", e)

    def _create_large_text_image(self, font_path: Optional[str]) -> None:
        """大きなテキスト画像を生成."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            img = Image.new('RGB', (800, 150), color='black')
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype(font_path, 20) if font_path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            lines = self.expected_results["large_text"].split('\n')
            y_offset = 30
            for line in lines:
                draw.text((50, y_offset), line, fill='white', font=font)
                y_offset += 40

            img.save(self.base_dir / self.images["large_text"])

        except Exception as e:
            logger.warning("大テキスト画像の生成に失敗: %s", e)

    def _create_complex_scene_image(self, font_path: Optional[str]) -> None:
        """複雑な背景の画像を生成."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import random

            img = Image.new('RGB', (600, 200), color='darkblue')
            draw = ImageDraw.Draw(img)

            # 背景にノイズを追加
            for _ in range(100):
                x = random.randint(0, 600)
                y = random.randint(0, 200)
                color = (random.randint(0, 100), random.randint(0, 100), random.randint(100, 255))
                draw.ellipse([x, y, x+20, y+20], fill=color)

            try:
                font = ImageFont.truetype(font_path, 24) if font_path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            # 白い縁取りテキスト
            text = self.expected_results["complex_scene"]
            x, y = 50, 80

            # 縁取り効果
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        draw.text((x+dx, y+dy), text, fill='black', font=font)

            draw.text((x, y), text, fill='white', font=font)
            img.save(self.base_dir / self.images["complex_scene"])

        except Exception as e:
            logger.warning("複雑背景画像の生成に失敗: %s", e)

    def _create_high_res_image(self, font_path: Optional[str]) -> None:
        """高解像度画像を生成."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            img = Image.new('RGB', (1920, 300), color='black')
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            draw.text((100, 120), self.expected_results["high_res"], fill='white', font=font)
            img.save(self.base_dir / self.images["high_res"])

        except Exception as e:
            logger.warning("高解像度画像の生成に失敗: %s", e)

    def _create_multi_language_image(self, font_path: Optional[str]) -> None:
        """多言語混在画像を生成."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            img = Image.new('RGB', (600, 120), color='black')
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype(font_path, 24) if font_path else ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            draw.text((50, 45), self.expected_results["multi_language"], fill='white', font=font)
            img.save(self.base_dir / self.images["multi_language"])

        except Exception as e:
            logger.warning("多言語画像の生成に失敗: %s", e)

    def _create_dummy_images(self) -> None:
        """テスト用のダミー画像ファイルを作成."""
        for filename in self.images.values():
            dummy_path = self.base_dir / filename
            try:
                dummy_path.touch()
                logger.debug("ダミー画像ファイルを作成: %s", dummy_path)
            except Exception as e:
                logger.warning("ダミー画像作成に失敗 %s: %s", dummy_path, e)


def calculate_text_similarity(expected: str, actual: str) -> float:
    """テキストの類似度を計算（0-1）."""
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0

    # 簡単な文字一致率で計算
    expected_chars = set(expected.lower().replace(' ', '').replace('\n', ''))
    actual_chars = set(actual.lower().replace(' ', '').replace('\n', ''))

    if not expected_chars:
        return 1.0 if not actual_chars else 0.0

    intersection = len(expected_chars & actual_chars)
    union = len(expected_chars | actual_chars)

    return intersection / union if union > 0 else 0.0


def get_memory_usage() -> float:
    """現在のメモリ使用量を取得（MB）."""
    if not PSUTIL_AVAILABLE:
        return 0.0

    try:
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0


def get_cpu_info() -> str:
    """CPU情報を取得."""
    try:
        # CPU profilerを使用してより詳細な情報を取得
        from app.core.cpu_profiler import CPUProfiler
        profiler = CPUProfiler()
        profile = profiler.detect_cpu_profile()
        return f"{profile.vendor} {profile.name} ({profile.cores_physical}/{profile.cores_logical} cores)"
    except ImportError:
        # フォールバック
        return f"{platform.processor()} ({os.cpu_count()} cores)"


def get_current_thread_config() -> Dict[str, Any]:
    """現在のスレッド設定を取得."""
    thread_vars = [
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "INTEL_NUM_THREADS",
        "OPENBLAS_CORETYPE",
    ]

    config = {}
    for var in thread_vars:
        value = os.environ.get(var)
        if value is not None:
            config[var] = value

    return config


class OCRBenchmark:
    """OCR性能ベンチマーククラス."""

    def __init__(self, ocr_engine=None, image_set: Optional[BenchmarkImageSet] = None):
        """初期化.

        Args:
            ocr_engine: OCRエンジンインスタンス
            image_set: ベンチマーク画像セット
        """
        self.ocr_engine = ocr_engine
        self.image_set = image_set or BenchmarkImageSet()

    def run_full_benchmark(self) -> BenchmarkResult:
        """包括的なベンチマーク実行."""
        if self.ocr_engine is None:
            raise ValueError("OCRエンジンが設定されていません")

        logger.info("OCRベンチマーク開始: %s", platform.system())

        # 画像存在確認
        image_status = self.image_set.verify_images_exist()
        missing_images = [key for key, exists in image_status.items() if not exists]

        if missing_images:
            logger.warning("存在しない画像: %s", missing_images)
            # サンプル画像を生成
            self.image_set.create_sample_images()

        processing_times = {}
        accuracy_scores = {}
        errors = {}

        # ベンチマーク開始時のベースラインメモリを測定
        baseline_memory = get_memory_usage()
        peak_memory = baseline_memory

        # 各テスト画像でベンチマーク実行
        for image_key in self.image_set.list_available_images():
            image_path = self.image_set.get_image_path(image_key)

            if not image_path.exists():
                errors[image_key] = f"画像ファイルが存在しません: {image_path}"
                continue

            logger.info("ベンチマーク実行中: %s", image_key)

            start_time = time.time()

            try:
                # OCR実行
                ocr_result = self.ocr_engine.extract_text(str(image_path))
                processing_time = time.time() - start_time

                # 結果の処理
                if isinstance(ocr_result, list) and ocr_result:
                    # OCRResultのリストの場合
                    extracted_text = ' '.join([result.text for result in ocr_result if hasattr(result, 'text')])
                elif isinstance(ocr_result, str):
                    extracted_text = ocr_result
                else:
                    extracted_text = ""

                # 精度計算
                expected_text = self.image_set.get_expected_result(image_key)
                accuracy = calculate_text_similarity(expected_text, extracted_text)

                processing_times[image_key] = processing_time
                accuracy_scores[image_key] = accuracy

                # 絶対的なピークメモリ使用量を追跡
                current_memory = get_memory_usage()
                peak_memory = max(peak_memory, current_memory)

                logger.debug("結果 %s: 時間=%.3fs, 精度=%.3f, 期待=\"%s\", 実際=\"%s\"",
                           image_key, processing_time, accuracy, expected_text, extracted_text)

            except Exception as e:
                error_msg = f"OCR処理エラー: {e}"
                errors[image_key] = error_msg
                logger.error("ベンチマークエラー %s: %s", image_key, error_msg)

        # 結果をまとめて返す
        # ベースラインからの最大増加量を計算
        max_memory_increase = peak_memory - baseline_memory

        return BenchmarkResult(
            platform=platform.system(),
            cpu_info=get_cpu_info(),
            processing_time=processing_times,
            accuracy_score=accuracy_scores,
            memory_usage=max_memory_increase,
            thread_config=get_current_thread_config(),
            ocr_settings=self._get_ocr_settings(),
            timestamp=datetime.now().isoformat(),
            errors=errors
        )

    def _get_ocr_settings(self) -> Dict[str, Any]:
        """OCRエンジンの設定を取得."""
        if not hasattr(self.ocr_engine, '__dict__'):
            return {}

        settings = {}
        for attr in ['language', 'confidence_threshold', 'max_batch_size']:
            if hasattr(self.ocr_engine, attr):
                settings[attr] = getattr(self.ocr_engine, attr)

        return settings

    def run_quick_benchmark(self, image_keys: Optional[List[str]] = None) -> BenchmarkResult:
        """クイックベンチマーク実行（指定画像のみ）."""
        if image_keys is None:
            image_keys = ["small_text", "large_text"]  # 基本的な2つのテストのみ

        # 一時的に画像セットを制限
        original_images = self.image_set.images.copy()
        original_results = self.image_set.expected_results.copy()

        try:
            # 指定された画像のみに制限
            self.image_set.images = {k: v for k, v in original_images.items() if k in image_keys}
            self.image_set.expected_results = {k: v for k, v in original_results.items() if k in image_keys}

            return self.run_full_benchmark()

        finally:
            # 元の設定に戻す
            self.image_set.images = original_images
            self.image_set.expected_results = original_results


class BenchmarkComparison:
    """プラットフォーム間ベンチマーク比較クラス."""

    def __init__(self):
        """初期化."""
        # Linux基準値（理想的な環境での参考値）
        self.linux_baseline = {
            "small_text": 0.5,      # 秒
            "large_text": 0.8,      # 秒
            "complex_scene": 1.2,   # 秒
            "high_res": 2.0,        # 秒
            "multi_language": 1.0,  # 秒
        }

    def compare_with_baseline(self, result: BenchmarkResult) -> ComparisonReport:
        """理想的なLinux環境との比較レポート生成."""
        performance_ratios = {}
        recommendations = []

        for image_key, user_time in result.processing_time.items():
            baseline_time = self.linux_baseline.get(image_key, 1.0)
            if user_time > 0:
                # 性能比率（1.0より大きいほど高速）
                performance_ratios[image_key] = baseline_time / user_time
            else:
                performance_ratios[image_key] = 0.0

        # 総合性能比率
        overall_performance = statistics.mean(performance_ratios.values()) if performance_ratios else 0.0

        # 推奨事項生成
        if overall_performance < 0.2:  # 5倍以上遅い
            recommendations.append("重大な性能問題が検出されました。システム設定を確認してください。")
        elif overall_performance < 0.5:  # 2倍以上遅い
            recommendations.append("性能改善の余地があります。最適化設定の適用を検討してください。")
        elif overall_performance > 2.0:  # 2倍以上高速
            recommendations.append("優秀な性能です。現在の設定を維持してください。")

        # 改善効果推定
        estimated_improvement = self._estimate_improvement_potential(result, overall_performance)

        return ComparisonReport(
            overall_performance_ratio=overall_performance,
            detailed_comparison=performance_ratios,
            recommendations=recommendations,
            estimated_improvement=estimated_improvement
        )

    def _estimate_improvement_potential(self, result: BenchmarkResult, current_performance: float) -> str:
        """改善効果の推定."""
        if current_performance >= 1.5:
            return "現在の性能は良好です"

        platform = result.platform
        cpu_info = result.cpu_info.lower()

        if platform == "Windows":
            if "intel" in cpu_info and "10" in cpu_info:
                return "Issue #129の最適化により5-15倍の性能向上が期待できます"
            elif "amd" in cpu_info and "ryzen" in cpu_info:
                return "AMD最適化により3-8倍の性能向上が期待できます"
            else:
                return "Windows最適化により2-5倍の性能向上が期待できます"

        elif platform == "Darwin":
            if "apple" in cpu_info or "m1" in cpu_info or "m2" in cpu_info:
                return "Apple Silicon最適化により3-10倍の性能向上が期待できます"
            else:
                return "macOS最適化により2-4倍の性能向上が期待できます"

        else:  # Linux
            return "適応的スレッド設定により1.5-3倍の性能向上が期待できます"


class PerformanceDiagnostics:
    """性能診断クラス."""

    def diagnose_performance_issues(self, result: BenchmarkResult) -> List[Issue]:
        """性能問題を自動診断."""
        issues = []

        # 処理時間の問題を診断
        issues.extend(self._diagnose_processing_time_issues(result))

        # 精度の問題を診断
        issues.extend(self._diagnose_accuracy_issues(result))

        # メモリ使用量の問題を診断
        issues.extend(self._diagnose_memory_issues(result))

        # プラットフォーム固有の問題を診断
        issues.extend(self._diagnose_platform_specific_issues(result))

        return issues

    def _diagnose_processing_time_issues(self, result: BenchmarkResult) -> List[Issue]:
        """処理時間の問題を診断."""
        issues = []

        if not result.processing_time:
            return issues

        avg_time = statistics.mean(result.processing_time.values())
        max_time = max(result.processing_time.values())

        # 異常に遅い処理時間
        if avg_time > 10.0:
            issues.append(Issue(
                severity="Critical",
                description=f"平均処理時間が異常に遅い: {avg_time:.2f}秒",
                recommendation="OCRエンジンの設定を確認し、最適化を適用してください",
                estimated_improvement="5-20倍の性能向上が期待できます"
            ))
        elif avg_time > 5.0:
            issues.append(Issue(
                severity="High",
                description=f"処理時間が遅い: {avg_time:.2f}秒",
                recommendation="Issue #130の適応的スレッド設定を適用してください",
                estimated_improvement="2-5倍の性能向上が期待できます"
            ))

        # 特定の画像で極端に遅い
        for image_key, time_taken in result.processing_time.items():
            if time_taken > avg_time * 3:
                issues.append(Issue(
                    severity="Medium",
                    description=f"{image_key}の処理が他より極端に遅い: {time_taken:.2f}秒",
                    recommendation="画像の複雑さに応じた設定調整が必要です",
                    estimated_improvement="特定画像の処理時間短縮"
                ))

        return issues

    def _diagnose_accuracy_issues(self, result: BenchmarkResult) -> List[Issue]:
        """精度の問題を診断."""
        issues = []

        if not result.accuracy_score:
            return issues

        avg_accuracy = statistics.mean(result.accuracy_score.values())

        if avg_accuracy < 0.3:
            issues.append(Issue(
                severity="High",
                description=f"認識精度が低い: {avg_accuracy:.1%}",
                recommendation="OCRエンジンの言語設定やしきい値を調整してください",
                estimated_improvement="認識精度の向上"
            ))
        elif avg_accuracy < 0.6:
            issues.append(Issue(
                severity="Medium",
                description=f"認識精度に改善の余地があります: {avg_accuracy:.1%}",
                recommendation="画像前処理やOCR設定の最適化を検討してください",
                estimated_improvement="認識精度の向上"
            ))

        return issues

    def _diagnose_memory_issues(self, result: BenchmarkResult) -> List[Issue]:
        """メモリ使用量の問題を診断."""
        issues = []

        if result.memory_usage > 1000:  # 1GB以上
            issues.append(Issue(
                severity="Medium",
                description=f"メモリ使用量が大きい: {result.memory_usage:.1f}MB",
                recommendation="バッチサイズの調整やメモリ最適化設定を検討してください",
                estimated_improvement="メモリ使用量の削減"
            ))

        return issues

    def _diagnose_platform_specific_issues(self, result: BenchmarkResult) -> List[Issue]:
        """プラットフォーム固有の問題を診断."""
        issues = []
        platform = result.platform
        cpu_info = result.cpu_info.lower()

        if platform == "Windows":
            # Windows固有の問題
            if any(t > 5.0 for t in result.processing_time.values()):
                issues.append(Issue(
                    severity="High",
                    description="Windows環境でOCR処理が異常に遅い",
                    recommendation="Issue #129のWindows最適化を適用してください",
                    estimated_improvement="5-15倍の性能向上"
                ))

            # Intel CPU特有の問題
            if "intel" in cpu_info:
                thread_config = result.thread_config
                omp_threads = thread_config.get("OMP_NUM_THREADS")

                # OMP_NUM_THREADSを安全に数値変換
                omp_threads_num = None
                if omp_threads:
                    try:
                        omp_threads_num = int(omp_threads)
                    except (ValueError, TypeError):
                        # "auto"やカンマ区切り値などの場合は無視
                        pass

                if not omp_threads or omp_threads_num is None or omp_threads_num < 4:
                    issues.append(Issue(
                        severity="Medium",
                        description="Intel CPUでスレッド数が最適化されていない",
                        recommendation="適応的スレッド設定を有効にしてください",
                        estimated_improvement="2-4倍の性能向上"
                    ))

        elif platform == "Darwin":
            # Apple Silicon特有の問題
            if ("apple" in cpu_info or "m1" in cpu_info or "m2" in cpu_info):
                if any(t == 0 for t in result.processing_time.values()):
                    issues.append(Issue(
                        severity="Critical",
                        description="Apple Silicon環境でOCRがフリーズしている",
                        recommendation="Issue #128のApple Silicon対応を適用してください",
                        estimated_improvement="動作可能 + 3-10倍高速化"
                    ))

                # VECLIBの設定確認
                thread_config = result.thread_config
                if "VECLIB_MAXIMUM_THREADS" not in thread_config:
                    issues.append(Issue(
                        severity="Medium",
                        description="Apple SiliconでVECLIB最適化が無効",
                        recommendation="適応的スレッド設定でApple Silicon最適化を有効にしてください",
                        estimated_improvement="2-5倍の性能向上"
                    ))

        return issues


class BenchmarkReportGenerator:
    """ベンチマークレポート生成クラス."""

    def generate_text_report(self, result: BenchmarkResult, comparison: Optional[ComparisonReport] = None, issues: Optional[List[Issue]] = None) -> str:
        """テキスト形式のレポート生成."""
        lines = []
        lines.append("=" * 60)
        lines.append("OCRベンチマークレポート")
        lines.append("=" * 60)
        lines.append(f"実行日時: {result.timestamp}")
        lines.append(f"プラットフォーム: {result.platform}")
        lines.append(f"CPU: {result.cpu_info}")
        lines.append("")

        # 総合スコア
        overall_score = result.overall_performance_score()
        lines.append(f"総合性能スコア: {overall_score:.1f}/100")
        lines.append("")

        # 処理時間結果
        lines.append("処理時間:")
        for image_key, time_taken in result.processing_time.items():
            lines.append(f"  {image_key}: {time_taken:.3f}秒")

        if result.processing_time:
            avg_time = statistics.mean(result.processing_time.values())
            lines.append(f"  平均: {avg_time:.3f}秒")
        lines.append("")

        # 精度結果
        lines.append("認識精度:")
        for image_key, accuracy in result.accuracy_score.items():
            lines.append(f"  {image_key}: {accuracy:.1%}")

        if result.accuracy_score:
            avg_accuracy = statistics.mean(result.accuracy_score.values())
            lines.append(f"  平均: {avg_accuracy:.1%}")
        lines.append("")

        # メモリ使用量
        lines.append(f"メモリ使用量: {result.memory_usage:.1f}MB")
        lines.append("")

        # スレッド設定
        lines.append("スレッド設定:")
        for key, value in result.thread_config.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

        # 比較結果
        if comparison:
            lines.append("性能比較:")
            lines.append(f"  総合性能比率: {comparison.overall_performance_ratio:.2f}x")
            for image_key, ratio in comparison.detailed_comparison.items():
                lines.append(f"  {image_key}: {ratio:.2f}x")
            lines.append("")

            lines.append("推奨事項:")
            for recommendation in comparison.recommendations:
                lines.append(f"  • {recommendation}")
            lines.append("")

            lines.append(f"期待される改善効果: {comparison.estimated_improvement}")
            lines.append("")

        # 診断結果
        if issues:
            lines.append("診断結果:")
            for issue in issues:
                lines.append(f"  [{issue.severity}] {issue.description}")
                lines.append(f"    推奨対処法: {issue.recommendation}")
                lines.append(f"    期待効果: {issue.estimated_improvement}")
                lines.append("")

        # エラー情報
        if result.errors:
            lines.append("エラー:")
            for image_key, error in result.errors.items():
                lines.append(f"  {image_key}: {error}")
            lines.append("")

        return "\n".join(lines)

    def generate_csv_data(self, results: List[BenchmarkResult]) -> str:
        """CSV形式での詳細データエクスポート."""
        lines = []

        # ヘッダー
        header = ["timestamp", "platform", "cpu_info", "overall_score", "memory_usage"]

        # 画像別の処理時間と精度のカラム
        if results:
            sample_result = results[0]
            for image_key in sample_result.processing_time.keys():
                header.extend([f"{image_key}_time", f"{image_key}_accuracy"])

        lines.append(",".join(header))

        # データ行
        for result in results:
            row = [
                result.timestamp,
                result.platform,
                result.cpu_info.replace(",", ";"),  # CSVのカンマエスケープ
                f"{result.overall_performance_score():.2f}",
                f"{result.memory_usage:.1f}"
            ]

            for image_key in sample_result.processing_time.keys():
                time_taken = result.processing_time.get(image_key, 0)
                accuracy = result.accuracy_score.get(image_key, 0)
                row.extend([f"{time_taken:.3f}", f"{accuracy:.3f}"])

            lines.append(",".join(row))

        return "\n".join(lines)

    def export_json_data(self, results: List[BenchmarkResult]) -> str:
        """JSON形式での詳細データエクスポート."""
        data = [result.to_dict() for result in results]
        return json.dumps(data, indent=2, ensure_ascii=False)


class BenchmarkManager:
    """ベンチマーク結果の管理クラス."""

    def __init__(self, storage_dir: Optional[Path] = None):
        """初期化.

        Args:
            storage_dir: ベンチマーク結果保存ディレクトリ
        """
        if storage_dir is None:
            storage_dir = Path.home() / ".vlog-subs-tool" / "benchmarks"

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_result(self, result: BenchmarkResult) -> Path:
        """ベンチマーク結果を保存."""
        # ファイル名生成（タイムスタンプ + プラットフォーム）
        timestamp = datetime.fromisoformat(result.timestamp)
        filename = f"benchmark_{result.platform}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"

        filepath = self.storage_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info("ベンチマーク結果を保存: %s", filepath)
        return filepath

    def load_results(self, limit: Optional[int] = None) -> List[BenchmarkResult]:
        """保存されたベンチマーク結果を読み込み."""
        results = []

        json_files = list(self.storage_dir.glob("benchmark_*.json"))
        # 作成日時でソート（新しい順）
        json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        if limit:
            json_files = json_files[:limit]

        for filepath in json_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # BenchmarkResultオブジェクトに復元
                result = BenchmarkResult(**data)
                results.append(result)

            except Exception as e:
                logger.warning("ベンチマーク結果の読み込みに失敗: %s - %s", filepath, e)

        return results

    def get_platform_results(self, platform: str, limit: Optional[int] = None) -> List[BenchmarkResult]:
        """特定プラットフォームの結果を取得."""
        all_results = self.load_results()
        platform_results = [r for r in all_results if r.platform == platform]

        if limit:
            platform_results = platform_results[:limit]

        return platform_results

    def get_latest_result(self, platform: Optional[str] = None) -> Optional[BenchmarkResult]:
        """最新のベンチマーク結果を取得."""
        if platform:
            results = self.get_platform_results(platform, limit=1)
        else:
            results = self.load_results(limit=1)

        return results[0] if results else None

    def cleanup_old_results(self, keep_count: int = 10) -> int:
        """古いベンチマーク結果を削除."""
        json_files = list(self.storage_dir.glob("benchmark_*.json"))
        json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        # 保持数を超えるファイルを削除
        deleted_count = 0
        for filepath in json_files[keep_count:]:
            try:
                filepath.unlink()
                deleted_count += 1
            except Exception as e:
                logger.warning("ファイル削除に失敗: %s - %s", filepath, e)

        if deleted_count > 0:
            logger.info("古いベンチマーク結果を%d件削除しました", deleted_count)

        return deleted_count


def run_comprehensive_analysis(ocr_engine) -> Dict[str, Any]:
    """包括的なOCR性能分析を実行."""
    logger.info("包括的OCR性能分析を開始")

    # ベンチマーク実行
    benchmark = OCRBenchmark(ocr_engine)
    result = benchmark.run_full_benchmark()

    # 比較分析
    comparison = BenchmarkComparison()
    comparison_report = comparison.compare_with_baseline(result)

    # 診断実行
    diagnostics = PerformanceDiagnostics()
    issues = diagnostics.diagnose_performance_issues(result)

    # レポート生成
    report_generator = BenchmarkReportGenerator()
    text_report = report_generator.generate_text_report(result, comparison_report, issues)

    # 結果保存
    manager = BenchmarkManager()
    saved_path = manager.save_result(result)

    return {
        "result": result,
        "comparison": comparison_report,
        "issues": issues,
        "text_report": text_report,
        "saved_path": saved_path
    }