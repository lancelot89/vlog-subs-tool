#!/usr/bin/env python3
"""PaddleOCR Parameter Optimization Benchmark Tool

Issue #176用ベンチマークツール
PaddleOCRのdet_limit_side_lenとrec_batch_numパラメータを最適化し、
精度を維持しつつ処理速度を最大化する最適な組み合わせを発見する。

Usage:
    python benchmark_paddleocr_parameter_optimization.py [options]
"""

import argparse
import json
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

warnings.filterwarnings("ignore")


@dataclass
class ParameterCombination:
    """PaddleOCRパラメータの組み合わせ"""

    det_limit_side_len: int
    rec_batch_num: int
    max_text_length: int = 100


@dataclass
class OCRBenchmarkResult:
    """OCRベンチマーク結果"""

    parameter_combination: ParameterCombination
    processing_time_ms: float
    detected_text_count: int
    confidence_scores: List[float]
    average_confidence: float
    memory_usage_mb: float
    platform: str


@dataclass
class OptimizationReport:
    """最適化レポート"""

    baseline_result: OCRBenchmarkResult
    optimization_results: List[OCRBenchmarkResult]
    best_combination: ParameterCombination
    performance_improvement_percent: float
    accuracy_maintained: bool
    recommendations: List[str]


class PaddleOCRParameterOptimizer:
    """PaddleOCRパラメータ最適化ベンチマーク"""

    def __init__(self, test_video_path: Optional[str] = None, language: str = "ja"):
        self.test_video_path = test_video_path
        self.language = language
        self.baseline_combination = ParameterCombination(
            det_limit_side_len=960, rec_batch_num=6, max_text_length=100
        )

    def create_test_image(self) -> np.ndarray:
        """テスト用の日本語字幕画像を生成"""
        # 白地に黒文字のテスト画像を作成
        img = np.ones((200, 800, 3), dtype=np.uint8) * 255

        # OpenCVで日本語テキストを描画（代替として英語で代用）
        text = "Sample Japanese subtitle text for OCR testing"
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(img, text, (50, 100), font, 1, (0, 0, 0), 2, cv2.LINE_AA)

        # ノイズを追加してよりリアルな条件にする
        noise = np.random.randint(0, 30, img.shape, dtype=np.uint8)
        img = cv2.add(img, noise)

        return img

    def extract_test_frames(self, video_path: str, frame_count: int = 5) -> List[np.ndarray]:
        """テスト動画からフレームを抽出"""
        frames = []
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            print(f"警告: 動画ファイル {video_path} を開けませんでした")
            return [self.create_test_image() for _ in range(frame_count)]

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_step = max(1, total_frames // frame_count)

        for i in range(0, total_frames, frame_step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
            if len(frames) >= frame_count:
                break

        cap.release()

        if not frames:
            print("動画からフレームを抽出できませんでした。テスト画像を使用します。")
            frames = [self.create_test_image() for _ in range(frame_count)]

        return frames

    def measure_memory_usage(self) -> float:
        """現在のメモリ使用量を測定（MB）"""
        try:
            import psutil

            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0

    def run_ocr_benchmark(
        self, frames: List[np.ndarray], params: ParameterCombination
    ) -> OCRBenchmarkResult:
        """指定されたパラメータでOCRベンチマークを実行"""
        try:
            from paddleocr import PaddleOCR

            # PaddleOCRを指定されたパラメータで初期化
            ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self.language,
                det_limit_side_len=params.det_limit_side_len,
                rec_batch_num=params.rec_batch_num,
                max_text_length=params.max_text_length,
                show_log=False,
            )

            memory_before = self.measure_memory_usage()
            start_time = time.perf_counter()

            detected_texts = []
            all_confidences = []

            for frame in frames:
                try:
                    result = ocr.ocr(frame, cls=True)
                    if result and result[0]:
                        for line in result[0]:
                            if len(line) >= 2 and isinstance(line[1], tuple):
                                text, confidence = line[1]
                                if text and text.strip():
                                    detected_texts.append(text.strip())
                                    all_confidences.append(confidence)
                except Exception as e:
                    print(f"OCR処理中にエラーが発生: {e}")
                    continue

            end_time = time.perf_counter()
            memory_after = self.measure_memory_usage()

            processing_time_ms = (end_time - start_time) * 1000
            avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
            memory_usage = max(0, memory_after - memory_before)

            import platform

            return OCRBenchmarkResult(
                parameter_combination=params,
                processing_time_ms=processing_time_ms,
                detected_text_count=len(detected_texts),
                confidence_scores=all_confidences,
                average_confidence=avg_confidence,
                memory_usage_mb=memory_usage,
                platform=platform.system(),
            )

        except ImportError:
            print("エラー: PaddleOCRが利用できません")
            return OCRBenchmarkResult(
                parameter_combination=params,
                processing_time_ms=0.0,
                detected_text_count=0,
                confidence_scores=[],
                average_confidence=0.0,
                memory_usage_mb=0.0,
                platform="Unknown",
            )
        except Exception as e:
            print(f"ベンチマーク実行中にエラーが発生: {e}")
            return OCRBenchmarkResult(
                parameter_combination=params,
                processing_time_ms=float("inf"),
                detected_text_count=0,
                confidence_scores=[],
                average_confidence=0.0,
                memory_usage_mb=0.0,
                platform="Error",
            )

    def generate_parameter_combinations(
        self,
        det_side_lens: List[int],
        batch_nums: List[int],
        max_text_lengths: List[int],
    ) -> List[ParameterCombination]:
        """パラメータの組み合わせを生成"""
        combinations = []
        for det_len in det_side_lens:
            for batch_num in batch_nums:
                for max_len in max_text_lengths:
                    combinations.append(
                        ParameterCombination(
                            det_limit_side_len=det_len,
                            rec_batch_num=batch_num,
                            max_text_length=max_len,
                        )
                    )
        return combinations

    def run_comprehensive_optimization(
        self,
        det_side_lens: List[int],
        batch_nums: List[int],
        max_text_lengths: List[int],
        accuracy_threshold: float = 0.95,
    ) -> OptimizationReport:
        """包括的な最適化ベンチマークを実行"""
        print("🔧 PaddleOCRパラメータ最適化ベンチマークを開始...")

        # テストフレームを準備
        if self.test_video_path and Path(self.test_video_path).exists():
            print(f"📹 テスト動画を使用: {self.test_video_path}")
            test_frames = self.extract_test_frames(self.test_video_path)
        else:
            print("📹 テスト画像を生成中...")
            test_frames = [self.create_test_image() for _ in range(3)]

        # ベースライン測定
        print("📏 ベースライン性能を測定中...")
        baseline_result = self.run_ocr_benchmark(test_frames, self.baseline_combination)
        print(
            f"   ベースライン: {baseline_result.processing_time_ms:.1f}ms, "
            f"精度: {baseline_result.average_confidence:.3f}"
        )

        # パラメータ組み合わせを生成
        combinations = self.generate_parameter_combinations(
            det_side_lens, batch_nums, max_text_lengths
        )
        print(f"🧪 {len(combinations)}通りのパラメータ組み合わせをテスト中...")

        # 各組み合わせでベンチマーク実行
        results = []
        best_result = baseline_result
        best_improvement = 0.0

        for i, params in enumerate(combinations, 1):
            print(
                f"   {i:2d}/{len(combinations)}: "
                f"det_len={params.det_limit_side_len}, "
                f"batch={params.rec_batch_num}, "
                f"max_len={params.max_text_length}"
            )

            result = self.run_ocr_benchmark(test_frames, params)

            # 精度が閾値以上で、処理時間が改善されている場合
            if (
                result.average_confidence >= accuracy_threshold
                and result.processing_time_ms < baseline_result.processing_time_ms
            ):
                improvement = (
                    (baseline_result.processing_time_ms - result.processing_time_ms)
                    / baseline_result.processing_time_ms
                    * 100
                )
                if improvement > best_improvement:
                    best_improvement = improvement
                    best_result = result

            results.append(result)

        # 推奨設定を生成
        recommendations = self._generate_recommendations(
            baseline_result, best_result, best_improvement
        )

        return OptimizationReport(
            baseline_result=baseline_result,
            optimization_results=results,
            best_combination=best_result.parameter_combination,
            performance_improvement_percent=best_improvement,
            accuracy_maintained=best_result.average_confidence >= accuracy_threshold,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        baseline: OCRBenchmarkResult,
        best: OCRBenchmarkResult,
        improvement: float,
    ) -> List[str]:
        """最適化結果に基づく推奨設定を生成"""
        recommendations = []

        if improvement > 30:
            recommendations.append(f"🚀 大幅な性能向上が期待できます（{improvement:.1f}%改善）")
            recommendations.append("推奨: この設定を標準として採用してください")
        elif improvement > 10:
            recommendations.append(f"📈 中程度の性能向上が見込めます（{improvement:.1f}%改善）")
            recommendations.append("推奨: 高速処理が必要な場面で使用を検討してください")
        elif improvement > 0:
            recommendations.append(f"✨ 軽微な性能向上があります（{improvement:.1f}%改善）")
            recommendations.append("推奨: 現在の設定を維持し、安定性を優先してください")
        else:
            recommendations.append("⚠️ 有意な性能向上は確認できませんでした")
            recommendations.append("推奨: 現在の設定を維持してください")

        # 詳細な設定推奨
        best_params = best.parameter_combination
        recommendations.append(
            f"最適パラメータ: det_limit_side_len={best_params.det_limit_side_len}, "
            f"rec_batch_num={best_params.rec_batch_num}, "
            f"max_text_length={best_params.max_text_length}"
        )

        return recommendations


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(
        description="PaddleOCRパラメータ最適化ベンチマーク",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 基本実行
  python benchmark_paddleocr_parameter_optimization.py

  # カスタムパラメータでテスト
  python benchmark_paddleocr_parameter_optimization.py \\
    --det-limit-side-lens 960,1280,1920 \\
    --rec-batch-nums 8,16,32 \\
    --test-video sample.mp4

  # 包括的最適化
  python benchmark_paddleocr_parameter_optimization.py \\
    --comprehensive \\
    --output optimization_results.json
        """,
    )

    parser.add_argument(
        "--det-limit-side-lens",
        type=str,
        default="640,960,1280,1920",
        help="テストするdet_limit_side_lenの値（カンマ区切り）",
    )

    parser.add_argument(
        "--rec-batch-nums",
        type=str,
        default="4,8,16,32",
        help="テストするrec_batch_numの値（カンマ区切り）",
    )

    parser.add_argument(
        "--max-text-lengths",
        type=str,
        default="50,100,200",
        help="テストするmax_text_lengthの値（カンマ区切り）",
    )

    parser.add_argument(
        "--test-video",
        type=str,
        help="テスト用動画ファイルのパス（指定しない場合は生成画像を使用）",
    )

    parser.add_argument(
        "--accuracy-threshold",
        type=float,
        default=0.95,
        help="許容可能な最低精度（デフォルト: 0.95）",
    )

    parser.add_argument("--output", type=str, help="結果を保存するJSONファイルのパス")

    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help="包括的な最適化ベンチマークを実行",
    )

    parser.add_argument(
        "--generate-config-recommendations",
        action="store_true",
        help="最適化結果に基づく設定推奨を生成",
    )

    return parser.parse_args()


def main():
    """メイン実行関数"""
    args = parse_arguments()

    # パラメータをパース
    det_side_lens = [int(x.strip()) for x in args.det_limit_side_lens.split(",")]
    batch_nums = [int(x.strip()) for x in args.rec_batch_nums.split(",")]
    max_text_lengths = [int(x.strip()) for x in args.max_text_lengths.split(",")]

    # オプティマイザーを初期化
    optimizer = PaddleOCRParameterOptimizer(test_video_path=args.test_video, language="ja")

    # ベンチマーク実行
    if args.comprehensive:
        report = optimizer.run_comprehensive_optimization(
            det_side_lens, batch_nums, max_text_lengths, args.accuracy_threshold
        )

        # 結果表示
        print("\n" + "=" * 60)
        print("🎯 PaddleOCRパラメータ最適化結果")
        print("=" * 60)
        print(f"ベースライン性能: {report.baseline_result.processing_time_ms:.1f}ms")
        print(f"最適化後性能: {report.best_combination}")
        print(f"性能向上率: {report.performance_improvement_percent:.1f}%")
        print(f"精度維持: {'✅' if report.accuracy_maintained else '❌'}")
        print("\n📋 推奨設定:")
        for rec in report.recommendations:
            print(f"  {rec}")

        # 結果を保存
        if args.output:
            output_data = {
                "report": asdict(report),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "test_parameters": {
                    "det_limit_side_lens": det_side_lens,
                    "rec_batch_nums": batch_nums,
                    "max_text_lengths": max_text_lengths,
                    "accuracy_threshold": args.accuracy_threshold,
                },
            }

            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            print(f"\n📁 結果を保存しました: {args.output}")

        # 設定推奨ファイルを生成
        if args.generate_config_recommendations:
            config_path = "paddleocr_optimized_config.json"
            config_data = {
                "det_limit_side_len": report.best_combination.det_limit_side_len,
                "rec_batch_num": report.best_combination.rec_batch_num,
                "max_text_length": report.best_combination.max_text_length,
                "performance_improvement": f"{report.performance_improvement_percent:.1f}%",
                "accuracy_maintained": report.accuracy_maintained,
            }

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            print(f"📁 最適化設定を保存しました: {config_path}")

    else:
        # 簡単なテスト実行
        print("🔧 簡単なパラメータテストを実行中...")
        test_frames = [optimizer.create_test_image() for _ in range(2)]
        test_params = ParameterCombination(
            det_limit_side_len=det_side_lens[0],
            rec_batch_num=batch_nums[0],
            max_text_length=max_text_lengths[0],
        )

        result = optimizer.run_ocr_benchmark(test_frames, test_params)
        print(f"テスト結果: {result.processing_time_ms:.1f}ms")
        print(f"検出テキスト数: {result.detected_text_count}")
        print(f"平均信頼度: {result.average_confidence:.3f}")


if __name__ == "__main__":
    main()
