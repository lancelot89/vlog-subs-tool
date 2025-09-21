#!/usr/bin/env python3
"""GPU Usage Validation Benchmark Tool

Issue #177用ベンチマークツール
Windows/WSL環境でのGPU利用状況の非対称性を検出・解消し、
統一された実行環境での公平な性能比較を実現する。

Usage:
    python benchmark_gpu_usage_validation.py [options]
"""

import argparse
import json
import os
import platform
import subprocess
import time
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

warnings.filterwarnings("ignore")


@dataclass
class GPUUsageInfo:
    """GPU使用状況情報"""

    gpu_available: bool
    gpu_count: int
    gpu_processes: List[Dict]
    gpu_memory_usage: float
    gpu_utilization: float
    cuda_available: bool
    paddle_gpu_enabled: bool


@dataclass
class EnvironmentInfo:
    """環境情報"""

    platform: str
    environment_type: str  # windows, wsl, linux
    gpu_info: GPUUsageInfo
    cpu_count: int
    memory_total_gb: float


@dataclass
class AsymmetryReport:
    """非対称性レポート"""

    windows_env: Optional[EnvironmentInfo]
    wsl_env: Optional[EnvironmentInfo]
    asymmetry_detected: bool
    asymmetry_details: List[str]
    recommended_action: str
    unified_config_suggestion: Dict


class GPUUsageValidator:
    """GPU利用状況検証ベンチマーク"""

    def __init__(self):
        self.current_platform = platform.system()
        self.environment_type = self._detect_environment_type()

    def _detect_environment_type(self) -> str:
        """実行環境タイプを検出"""
        if self.current_platform == "Windows":
            return "windows"
        elif self.current_platform == "Linux":
            # WSLかLinuxかを判定
            try:
                with open("/proc/version", "r") as f:
                    version_info = f.read().lower()
                if "microsoft" in version_info or "wsl" in version_info:
                    return "wsl"
                else:
                    return "linux"
            except FileNotFoundError:
                return "linux"
        else:
            return "other"

    def check_nvidia_smi_availability(self) -> bool:
        """nvidia-smiコマンドの利用可否を確認"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_gpu_usage_info(self) -> GPUUsageInfo:
        """現在のGPU使用状況を取得"""
        gpu_info = GPUUsageInfo(
            gpu_available=False,
            gpu_count=0,
            gpu_processes=[],
            gpu_memory_usage=0.0,
            gpu_utilization=0.0,
            cuda_available=False,
            paddle_gpu_enabled=False,
        )

        # nvidia-smiでGPU情報を取得
        if self.check_nvidia_smi_availability():
            try:
                # GPU基本情報
                gpu_query = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=count,memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if gpu_query.returncode == 0:
                    lines = gpu_query.stdout.strip().split("\n")
                    if lines and lines[0]:
                        # 最初のGPUの情報を使用
                        parts = lines[0].split(", ")
                        if len(parts) >= 3:
                            gpu_info.gpu_available = True
                            gpu_info.gpu_count = len(lines)
                            gpu_info.gpu_memory_usage = float(parts[1])
                            gpu_info.gpu_utilization = float(parts[2])

                # GPU使用プロセス情報
                process_query = subprocess.run(
                    ["nvidia-smi", "pmon", "-i", "0", "-s", "um", "-c", "1"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if process_query.returncode == 0:
                    gpu_info.gpu_processes = self._parse_gpu_processes(process_query.stdout)

            except subprocess.TimeoutExpired:
                print("警告: nvidia-smiコマンドがタイムアウトしました")
            except Exception as e:
                print(f"警告: GPU情報の取得中にエラーが発生: {e}")

        # PaddleのCUDA利用可否を確認
        try:
            import paddle

            gpu_info.cuda_available = paddle.is_compiled_with_cuda()
            if gpu_info.cuda_available:
                gpu_info.paddle_gpu_enabled = paddle.device.cuda.device_count() > 0
        except ImportError:
            print("警告: PaddlePaddleが利用できません")

        return gpu_info

    def _parse_gpu_processes(self, nvidia_smi_output: str) -> List[Dict]:
        """nvidia-smi pmonの出力をパース"""
        processes = []
        lines = nvidia_smi_output.strip().split("\n")

        for line in lines:
            if line.startswith("#") or not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 6:
                try:
                    process_info = {
                        "gpu_id": int(parts[0]),
                        "pid": int(parts[1]),
                        "process_name": parts[2],
                        "memory_usage": int(parts[4]) if parts[4] != "-" else 0,
                        "gpu_utilization": int(parts[5]) if parts[5] != "-" else 0,
                    }
                    processes.append(process_info)
                except (ValueError, IndexError):
                    continue

        return processes

    def get_environment_info(self) -> EnvironmentInfo:
        """現在の環境情報を取得"""
        gpu_info = self.get_gpu_usage_info()

        # CPU情報
        try:
            import psutil

            cpu_count = psutil.cpu_count(logical=False)
            memory_total = psutil.virtual_memory().total / (1024**3)
        except ImportError:
            cpu_count = os.cpu_count() or 1
            memory_total = 0.0

        return EnvironmentInfo(
            platform=self.current_platform,
            environment_type=self.environment_type,
            gpu_info=gpu_info,
            cpu_count=cpu_count,
            memory_total_gb=memory_total,
        )

    def monitor_gpu_during_ocr(self, duration_seconds: int = 30) -> List[GPUUsageInfo]:
        """OCR実行中のGPU使用状況を監視"""
        print(f"🔍 {duration_seconds}秒間のGPU使用状況を監視開始...")

        monitoring_results = []
        start_time = time.time()

        # 簡単なOCR処理を並行実行してGPU使用状況を監視
        import threading

        def run_sample_ocr():
            """サンプルOCR処理を実行"""
            try:
                from app.core.extractor.ocr import SimplePaddleOCREngine

                engine = SimplePaddleOCREngine(language="ja", confidence_threshold=0.5)
                if engine.initialize():
                    # テスト画像でOCR実行
                    test_img = np.ones((200, 400, 3), dtype=np.uint8) * 255
                    for _ in range(5):
                        engine.extract_text(test_img)
                        time.sleep(1)
            except Exception as e:
                print(f"OCR実行中にエラー: {e}")

        # OCRをバックグラウンドで実行
        ocr_thread = threading.Thread(target=run_sample_ocr)
        ocr_thread.daemon = True
        ocr_thread.start()

        # GPU使用状況を定期的に取得
        while time.time() - start_time < duration_seconds:
            gpu_info = self.get_gpu_usage_info()
            monitoring_results.append(gpu_info)
            time.sleep(2)

        print(f"✅ 監視完了: {len(monitoring_results)}回のサンプリング")
        return monitoring_results

    def detect_asymmetry(
        self, windows_data: Optional[EnvironmentInfo], wsl_data: Optional[EnvironmentInfo]
    ) -> AsymmetryReport:
        """Windows/WSL環境間の非対称性を検出"""
        asymmetry_details = []
        asymmetry_detected = False

        if not windows_data or not wsl_data:
            return AsymmetryReport(
                windows_env=windows_data,
                wsl_env=wsl_data,
                asymmetry_detected=False,
                asymmetry_details=["環境データが不足しています"],
                recommended_action="両環境でのデータ収集を完了してください",
                unified_config_suggestion={},
            )

        # GPU利用可否の非対称性をチェック
        win_gpu = windows_data.gpu_info.gpu_available
        wsl_gpu = wsl_data.gpu_info.gpu_available

        if win_gpu != wsl_gpu:
            asymmetry_detected = True
            asymmetry_details.append(f"GPU利用可否の差: Windows({win_gpu}) vs WSL({wsl_gpu})")

        # PaddleのGPU利用状況をチェック
        win_paddle_gpu = windows_data.gpu_info.paddle_gpu_enabled
        wsl_paddle_gpu = wsl_data.gpu_info.paddle_gpu_enabled

        if win_paddle_gpu != wsl_paddle_gpu:
            asymmetry_detected = True
            asymmetry_details.append(
                f"PaddleGPU利用の差: Windows({win_paddle_gpu}) vs WSL({wsl_paddle_gpu})"
            )

        # 推奨アクションを決定
        if asymmetry_detected:
            if win_gpu and wsl_gpu:
                recommended_action = "両環境でGPU利用に統一することを推奨"
                unified_config = {"force_gpu": True, "cuda_visible_devices": "0"}
            else:
                recommended_action = "両環境でCPU専用に統一することを推奨"
                unified_config = {"force_cpu": True, "cuda_visible_devices": "-1"}
        else:
            recommended_action = "環境は既に統一されています"
            unified_config = {"status": "unified"}

        return AsymmetryReport(
            windows_env=windows_data,
            wsl_env=wsl_data,
            asymmetry_detected=asymmetry_detected,
            asymmetry_details=asymmetry_details,
            recommended_action=recommended_action,
            unified_config_suggestion=unified_config,
        )

    def force_cpu_only(self):
        """CPU推論のみに強制設定"""
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
        os.environ["PADDLE_USE_GPU"] = "0"
        print("🔧 CPU専用モードに設定しました")

    def force_gpu_usage(self):
        """GPU推論に強制設定"""
        os.environ["CUDA_VISIBLE_DEVICES"] = "0"
        os.environ["PADDLE_USE_GPU"] = "1"
        print("🔧 GPU利用モードに設定しました")

    def run_comprehensive_benchmark(self, force_cpu: bool = False, force_gpu: bool = False) -> Dict:
        """包括的なベンチマークを実行"""
        if force_cpu:
            self.force_cpu_only()
        elif force_gpu:
            self.force_gpu_usage()

        print("🚀 包括的なGPU利用状況ベンチマークを開始...")

        # 環境情報を取得
        env_info = self.get_environment_info()

        # OCR実行中のGPU監視
        gpu_monitoring = self.monitor_gpu_during_ocr(duration_seconds=20)

        # 結果をまとめ
        benchmark_result = {
            "environment_info": asdict(env_info),
            "gpu_monitoring_samples": [asdict(sample) for sample in gpu_monitoring],
            "benchmark_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "forced_mode": {
                "cpu_only": force_cpu,
                "gpu_only": force_gpu,
            },
        }

        return benchmark_result


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(
        description="GPU利用状況検証ベンチマーク",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # GPU使用状況監視
  python benchmark_gpu_usage_validation.py --monitor-gpu

  # 環境比較分析
  python benchmark_gpu_usage_validation.py \\
    --compare-environments \\
    --detect-asymmetry

  # CPU統一での性能測定
  python benchmark_gpu_usage_validation.py \\
    --force-cpu-only \\
    --comprehensive-benchmark
        """,
    )

    parser.add_argument("--monitor-gpu", action="store_true", help="GPU使用状況を監視")

    parser.add_argument(
        "--environment",
        type=str,
        choices=["windows", "wsl", "linux"],
        help="環境タイプを明示的に指定",
    )

    parser.add_argument(
        "--compare-environments",
        action="store_true",
        help="異なる環境間での比較分析を実行",
    )

    parser.add_argument("--windows-data", type=str, help="Windows環境のデータファイルパス")

    parser.add_argument("--wsl-data", type=str, help="WSL環境のデータファイルパス")

    parser.add_argument("--detect-asymmetry", action="store_true", help="非対称性を検出・分析")

    parser.add_argument("--force-cpu-only", action="store_true", help="CPU専用モードで実行")

    parser.add_argument("--force-gpu-usage", action="store_true", help="GPU利用モードで実行")

    parser.add_argument(
        "--comprehensive-benchmark",
        action="store_true",
        help="包括的なベンチマークを実行",
    )

    parser.add_argument("--output", type=str, help="結果を保存するJSONファイルのパス")

    parser.add_argument("--duration", type=int, default=30, help="監視時間（秒）")

    return parser.parse_args()


def main():
    """メイン実行関数"""
    args = parse_arguments()

    validator = GPUUsageValidator()

    if args.monitor_gpu:
        print(f"🔍 GPU使用状況を監視中... ({args.duration}秒)")
        env_info = validator.get_environment_info()

        print("\n" + "=" * 50)
        print("📊 現在の環境情報")
        print("=" * 50)
        print(f"プラットフォーム: {env_info.platform}")
        print(f"環境タイプ: {env_info.environment_type}")
        print(f"GPU利用可能: {env_info.gpu_info.gpu_available}")
        print(f"GPU数: {env_info.gpu_info.gpu_count}")
        print(f"CUDA利用可能: {env_info.gpu_info.cuda_available}")
        print(f"PaddleGPU有効: {env_info.gpu_info.paddle_gpu_enabled}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(asdict(env_info), f, ensure_ascii=False, indent=2)
            print(f"\n📁 結果を保存しました: {args.output}")

    elif args.compare_environments and args.detect_asymmetry:
        print("🔍 環境間の非対称性を分析中...")

        windows_data = None
        wsl_data = None

        if args.windows_data and Path(args.windows_data).exists():
            with open(args.windows_data, "r", encoding="utf-8") as f:
                windows_raw = json.load(f)
                windows_data = EnvironmentInfo(**windows_raw)

        if args.wsl_data and Path(args.wsl_data).exists():
            with open(args.wsl_data, "r", encoding="utf-8") as f:
                wsl_raw = json.load(f)
                wsl_data = EnvironmentInfo(**wsl_raw)

        report = validator.detect_asymmetry(windows_data, wsl_data)

        print("\n" + "=" * 60)
        print("🎯 非対称性分析結果")
        print("=" * 60)
        print(f"非対称性検出: {'⚠️ あり' if report.asymmetry_detected else '✅ なし'}")
        if report.asymmetry_details:
            print("詳細:")
            for detail in report.asymmetry_details:
                print(f"  - {detail}")
        print(f"\n推奨アクション: {report.recommended_action}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(asdict(report), f, ensure_ascii=False, indent=2)
            print(f"\n📁 分析結果を保存しました: {args.output}")

    elif args.comprehensive_benchmark:
        print("🚀 包括的なベンチマークを実行中...")

        result = validator.run_comprehensive_benchmark(
            force_cpu=args.force_cpu_only, force_gpu=args.force_gpu_usage
        )

        print("\n" + "=" * 60)
        print("📈 ベンチマーク結果")
        print("=" * 60)
        env = result["environment_info"]
        print(f"環境: {env['environment_type']} ({env['platform']})")
        print(f"GPU利用: {env['gpu_info']['gpu_available']}")
        print(f"PaddleGPU: {env['gpu_info']['paddle_gpu_enabled']}")
        print(f"監視サンプル数: {len(result['gpu_monitoring_samples'])}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n📁 結果を保存しました: {args.output}")

    else:
        print("🔧 基本的な環境情報を表示中...")
        env_info = validator.get_environment_info()

        print("\n" + "=" * 50)
        print("📊 環境情報")
        print("=" * 50)
        print(f"プラットフォーム: {env_info.platform}")
        print(f"環境タイプ: {env_info.environment_type}")
        print(f"CPU数: {env_info.cpu_count}")
        print(f"メモリ: {env_info.memory_total_gb:.1f}GB")
        print(f"GPU利用可能: {env_info.gpu_info.gpu_available}")
        print(f"CUDA利用可能: {env_info.gpu_info.cuda_available}")
        print(f"PaddleGPU有効: {env_info.gpu_info.paddle_gpu_enabled}")


if __name__ == "__main__":
    main()
