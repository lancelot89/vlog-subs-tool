"""ベンチマークシステムの単体テスト.

OCRベンチマーク・診断機能の各コンポーネントをテストします。
Issue #131 - プラットフォーム別OCRベンチマーク・診断機能
"""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from app.core.benchmark import (
    BenchmarkResult,
    Issue,
    ComparisonReport,
    BenchmarkImageSet,
    OCRBenchmark,
    BenchmarkComparison,
    PerformanceDiagnostics,
    BenchmarkReportGenerator,
    BenchmarkManager,
    calculate_text_similarity,
    get_memory_usage,
    get_cpu_info,
    get_current_thread_config,
    run_comprehensive_analysis
)


class TestBenchmarkResult(unittest.TestCase):
    """BenchmarkResult のテスト."""

    def test_benchmark_result_creation(self):
        """BenchmarkResult の作成テスト."""
        result = BenchmarkResult(
            platform="Linux",
            cpu_info="Intel Core i7-10700K",
            processing_time={"small_text": 0.5, "large_text": 0.8},
            accuracy_score={"small_text": 0.9, "large_text": 0.85},
            memory_usage=150.0,
            thread_config={"OMP_NUM_THREADS": "4"},
            ocr_settings={"language": "ja"},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        self.assertEqual(result.platform, "Linux")
        self.assertEqual(result.cpu_info, "Intel Core i7-10700K")
        self.assertEqual(len(result.processing_time), 2)
        self.assertEqual(len(result.accuracy_score), 2)

    def test_overall_performance_score(self):
        """総合性能スコア計算のテスト."""
        result = BenchmarkResult(
            platform="Linux",
            cpu_info="Test CPU",
            processing_time={"test1": 1.0, "test2": 2.0},  # 平均1.5秒
            accuracy_score={"test1": 0.9, "test2": 0.8},   # 平均85%
            memory_usage=100.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        score = result.overall_performance_score()
        # 速度スコア: 10/1.5 = 6.67, 精度スコア: 85
        # 総合: (6.67 * 0.5 + 85 * 0.5) = 45.83
        self.assertAlmostEqual(score, 45.83, places=1)

    def test_to_dict(self):
        """辞書変換のテスト."""
        result = BenchmarkResult(
            platform="Linux",
            cpu_info="Test CPU",
            processing_time={"test": 1.0},
            accuracy_score={"test": 0.9},
            memory_usage=100.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        result_dict = result.to_dict()
        self.assertIsInstance(result_dict, dict)
        self.assertEqual(result_dict["platform"], "Linux")
        self.assertEqual(result_dict["processing_time"]["test"], 1.0)


class TestBenchmarkImageSet(unittest.TestCase):
    """BenchmarkImageSet のテスト."""

    def setUp(self):
        """テスト前の準備."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.image_set = BenchmarkImageSet(self.temp_dir)

    def tearDown(self):
        """テスト後のクリーンアップ."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_image_set_initialization(self):
        """画像セットの初期化テスト."""
        self.assertEqual(len(self.image_set.images), 5)
        self.assertEqual(len(self.image_set.expected_results), 5)
        self.assertIn("small_text", self.image_set.images)
        self.assertIn("large_text", self.image_set.images)

    def test_get_image_path(self):
        """画像パス取得のテスト."""
        path = self.image_set.get_image_path("small_text")
        expected_path = self.temp_dir / "sample_small_subtitle.png"
        self.assertEqual(path, expected_path)

        with self.assertRaises(ValueError):
            self.image_set.get_image_path("nonexistent")

    def test_get_expected_result(self):
        """期待結果取得のテスト."""
        result = self.image_set.get_expected_result("small_text")
        self.assertEqual(result, "こんにちは")

        result = self.image_set.get_expected_result("nonexistent")
        self.assertEqual(result, "")

    def test_list_available_images(self):
        """利用可能画像リスト取得のテスト."""
        images = self.image_set.list_available_images()
        self.assertEqual(len(images), 5)
        self.assertIn("small_text", images)
        self.assertIn("multi_language", images)

    def test_verify_images_exist(self):
        """画像存在確認のテスト."""
        # 存在しない状態
        status = self.image_set.verify_images_exist()
        self.assertEqual(len(status), 5)
        self.assertFalse(any(status.values()))

        # 1つの画像を作成
        (self.temp_dir / "sample_small_subtitle.png").touch()
        status = self.image_set.verify_images_exist()
        self.assertTrue(status["small_text"])
        self.assertFalse(status["large_text"])


class TestOCRBenchmark(unittest.TestCase):
    """OCRBenchmark のテスト."""

    def setUp(self):
        """テスト前の準備."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.image_set = BenchmarkImageSet(self.temp_dir)
        self.mock_ocr_engine = Mock()

    def tearDown(self):
        """テスト後のクリーンアップ."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_benchmark_initialization(self):
        """ベンチマーク初期化のテスト."""
        benchmark = OCRBenchmark(self.mock_ocr_engine, self.image_set)
        self.assertEqual(benchmark.ocr_engine, self.mock_ocr_engine)
        self.assertEqual(benchmark.image_set, self.image_set)

    def test_run_benchmark_no_engine(self):
        """OCRエンジンなしでのベンチマーク実行テスト."""
        benchmark = OCRBenchmark(None, self.image_set)
        with self.assertRaises(ValueError):
            benchmark.run_full_benchmark()

    @patch('app.core.benchmark.get_memory_usage')
    @patch('app.core.benchmark.get_cpu_info')
    @patch('app.core.benchmark.get_current_thread_config')
    def test_run_full_benchmark(self, mock_thread_config, mock_cpu_info, mock_memory):
        """フルベンチマーク実行のテスト."""
        # モックの設定
        mock_cpu_info.return_value = "Test CPU"
        mock_thread_config.return_value = {"OMP_NUM_THREADS": "4"}
        mock_memory.return_value = 100.0

        # テスト画像作成
        test_image = self.temp_dir / "sample_small_subtitle.png"
        test_image.touch()

        # OCRエンジンのモック設定
        mock_result = Mock()
        mock_result.text = "こんにちは"
        self.mock_ocr_engine.extract_text.return_value = [mock_result]

        # ベンチマーク実行
        benchmark = OCRBenchmark(self.mock_ocr_engine, self.image_set)
        result = benchmark.run_full_benchmark()

        # 結果検証
        self.assertIsInstance(result, BenchmarkResult)
        self.assertEqual(result.platform, "Linux")  # テスト環境依存
        self.assertIn("small_text", result.processing_time)
        self.assertIn("small_text", result.accuracy_score)

    def test_run_quick_benchmark(self):
        """クイックベンチマーク実行のテスト."""
        # テスト画像作成
        (self.temp_dir / "sample_small_subtitle.png").touch()
        (self.temp_dir / "sample_large_subtitle.png").touch()

        # OCRエンジンのモック設定
        mock_result = Mock()
        mock_result.text = "test"
        self.mock_ocr_engine.extract_text.return_value = [mock_result]

        benchmark = OCRBenchmark(self.mock_ocr_engine, self.image_set)

        with patch('app.core.benchmark.get_cpu_info'), \
             patch('app.core.benchmark.get_current_thread_config'), \
             patch('app.core.benchmark.get_memory_usage'):

            result = benchmark.run_quick_benchmark()

        # クイックベンチマークは2つの画像のみテスト
        self.assertEqual(len(result.processing_time), 2)
        self.assertIn("small_text", result.processing_time)
        self.assertIn("large_text", result.processing_time)


class TestBenchmarkComparison(unittest.TestCase):
    """BenchmarkComparison のテスト."""

    def test_compare_with_baseline(self):
        """基準値との比較テスト."""
        result = BenchmarkResult(
            platform="Windows",
            cpu_info="Intel Core i7-10700K",
            processing_time={"small_text": 1.0, "large_text": 1.6},  # 基準値の2倍遅い
            accuracy_score={"small_text": 0.9, "large_text": 0.8},
            memory_usage=100.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        comparison = BenchmarkComparison()
        report = comparison.compare_with_baseline(result)

        self.assertIsInstance(report, ComparisonReport)
        # 性能比率は0.5（2倍遅い）
        self.assertAlmostEqual(report.overall_performance_ratio, 0.5, places=1)
        # 性能が悪い場合は推奨事項が生成される
        if report.overall_performance_ratio < 0.5:
            self.assertGreater(len(report.recommendations), 0)
        self.assertIn("向上", report.estimated_improvement)

    def test_estimate_improvement_windows(self):
        """Windows改善効果推定のテスト."""
        comparison = BenchmarkComparison()

        # Intel CPUの場合
        result = BenchmarkResult(
            platform="Windows",
            cpu_info="Intel Core i7-10700K",
            processing_time={"test": 2.0},
            accuracy_score={"test": 0.9},
            memory_usage=100.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        improvement = comparison._estimate_improvement_potential(result, 0.3)
        self.assertIn("5-15倍", improvement)

        # AMD CPUの場合
        result.cpu_info = "AMD Ryzen 5 3600"
        improvement = comparison._estimate_improvement_potential(result, 0.3)
        self.assertIn("3-8倍", improvement)


class TestPerformanceDiagnostics(unittest.TestCase):
    """PerformanceDiagnostics のテスト."""

    def test_diagnose_processing_time_issues(self):
        """処理時間問題診断のテスト."""
        result = BenchmarkResult(
            platform="Linux",
            cpu_info="Test CPU",
            processing_time={"test1": 15.0, "test2": 2.0},  # 平均8.5秒（遅い）
            accuracy_score={"test1": 0.9, "test2": 0.8},
            memory_usage=100.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        diagnostics = PerformanceDiagnostics()
        issues = diagnostics._diagnose_processing_time_issues(result)

        self.assertGreater(len(issues), 0)
        # 平均8.5秒なので、処理時間の問題が検出されるはず（Critical または High）
        time_issues = [i for i in issues if "処理時間" in i.description or "遅い" in i.description]
        self.assertGreater(len(time_issues), 0)

    def test_diagnose_accuracy_issues(self):
        """精度問題診断のテスト."""
        result = BenchmarkResult(
            platform="Linux",
            cpu_info="Test CPU",
            processing_time={"test1": 1.0, "test2": 1.0},
            accuracy_score={"test1": 0.2, "test2": 0.1},  # 平均15%（低い）
            memory_usage=100.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        diagnostics = PerformanceDiagnostics()
        issues = diagnostics._diagnose_accuracy_issues(result)

        self.assertGreater(len(issues), 0)
        # 低精度の問題が検出されるはず
        high_issues = [i for i in issues if i.severity == "High"]
        self.assertGreater(len(high_issues), 0)

    def test_diagnose_platform_specific_windows(self):
        """Windows固有問題診断のテスト."""
        result = BenchmarkResult(
            platform="Windows",
            cpu_info="Intel Core i7-8700K",
            processing_time={"test": 8.0},  # 遅い
            accuracy_score={"test": 0.9},
            memory_usage=100.0,
            thread_config={"OMP_NUM_THREADS": "2"},  # 最適化されていない
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        diagnostics = PerformanceDiagnostics()
        issues = diagnostics._diagnose_platform_specific_issues(result)

        self.assertGreater(len(issues), 0)
        # Windows固有の問題が検出されるはず
        windows_issues = [i for i in issues if "Windows" in i.description]
        self.assertGreater(len(windows_issues), 0)

    def test_diagnose_platform_specific_apple_silicon(self):
        """Apple Silicon固有問題診断のテスト."""
        result = BenchmarkResult(
            platform="Darwin",
            cpu_info="Apple M2 Pro",
            processing_time={"test": 0.0},  # フリーズを示す
            accuracy_score={"test": 0.0},
            memory_usage=100.0,
            thread_config={},  # VECLIB設定なし
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        diagnostics = PerformanceDiagnostics()
        issues = diagnostics._diagnose_platform_specific_issues(result)

        self.assertGreater(len(issues), 0)
        # フリーズ問題が検出されるはず
        critical_issues = [i for i in issues if i.severity == "Critical"]
        self.assertGreater(len(critical_issues), 0)


class TestBenchmarkReportGenerator(unittest.TestCase):
    """BenchmarkReportGenerator のテスト."""

    def test_generate_text_report(self):
        """テキストレポート生成のテスト."""
        result = BenchmarkResult(
            platform="Linux",
            cpu_info="Test CPU",
            processing_time={"test": 1.0},
            accuracy_score={"test": 0.9},
            memory_usage=100.0,
            thread_config={"OMP_NUM_THREADS": "4"},
            ocr_settings={"language": "ja"},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        generator = BenchmarkReportGenerator()
        report = generator.generate_text_report(result)

        self.assertIsInstance(report, str)
        self.assertIn("OCRベンチマークレポート", report)
        self.assertIn("Linux", report)
        self.assertIn("Test CPU", report)
        self.assertIn("1.000秒", report)
        self.assertIn("90.0%", report)

    def test_generate_csv_data(self):
        """CSVデータ生成のテスト."""
        results = [
            BenchmarkResult(
                platform="Linux",
                cpu_info="Test CPU 1",
                processing_time={"test": 1.0},
                accuracy_score={"test": 0.9},
                memory_usage=100.0,
                thread_config={},
                ocr_settings={},
                timestamp="2025-01-01T12:00:00",
                errors={}
            ),
            BenchmarkResult(
                platform="Windows",
                cpu_info="Test CPU 2",
                processing_time={"test": 2.0},
                accuracy_score={"test": 0.8},
                memory_usage=150.0,
                thread_config={},
                ocr_settings={},
                timestamp="2025-01-01T13:00:00",
                errors={}
            )
        ]

        generator = BenchmarkReportGenerator()
        csv_data = generator.generate_csv_data(results)

        self.assertIsInstance(csv_data, str)
        lines = csv_data.split('\n')
        self.assertEqual(len(lines), 3)  # ヘッダー + 2データ行
        self.assertIn("timestamp", lines[0])
        self.assertIn("Linux", lines[1])
        self.assertIn("Windows", lines[2])

    def test_export_json_data(self):
        """JSONデータエクスポートのテスト."""
        results = [
            BenchmarkResult(
                platform="Linux",
                cpu_info="Test CPU",
                processing_time={"test": 1.0},
                accuracy_score={"test": 0.9},
                memory_usage=100.0,
                thread_config={},
                ocr_settings={},
                timestamp="2025-01-01T12:00:00",
                errors={}
            )
        ]

        generator = BenchmarkReportGenerator()
        json_data = generator.export_json_data(results)

        self.assertIsInstance(json_data, str)
        data = json.loads(json_data)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["platform"], "Linux")


class TestBenchmarkManager(unittest.TestCase):
    """BenchmarkManager のテスト."""

    def setUp(self):
        """テスト前の準備."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = BenchmarkManager(self.temp_dir)

    def tearDown(self):
        """テスト後のクリーンアップ."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_result(self):
        """結果保存・読み込みのテスト."""
        result = BenchmarkResult(
            platform="Linux",
            cpu_info="Test CPU",
            processing_time={"test": 1.0},
            accuracy_score={"test": 0.9},
            memory_usage=100.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        # 保存
        saved_path = self.manager.save_result(result)
        self.assertTrue(saved_path.exists())

        # 読み込み
        loaded_results = self.manager.load_results()
        self.assertEqual(len(loaded_results), 1)
        self.assertEqual(loaded_results[0].platform, "Linux")

    def test_get_platform_results(self):
        """プラットフォーム別結果取得のテスト."""
        # Linux結果を保存
        linux_result = BenchmarkResult(
            platform="Linux",
            cpu_info="Test CPU",
            processing_time={"test": 1.0},
            accuracy_score={"test": 0.9},
            memory_usage=100.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        # Windows結果を保存
        windows_result = BenchmarkResult(
            platform="Windows",
            cpu_info="Test CPU",
            processing_time={"test": 2.0},
            accuracy_score={"test": 0.8},
            memory_usage=150.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T13:00:00",
            errors={}
        )

        self.manager.save_result(linux_result)
        self.manager.save_result(windows_result)

        # Linux結果のみ取得
        linux_results = self.manager.get_platform_results("Linux")
        self.assertEqual(len(linux_results), 1)
        self.assertEqual(linux_results[0].platform, "Linux")

        # Windows結果のみ取得
        windows_results = self.manager.get_platform_results("Windows")
        self.assertEqual(len(windows_results), 1)
        self.assertEqual(windows_results[0].platform, "Windows")

    def test_cleanup_old_results(self):
        """古い結果削除のテスト."""
        # 5つの結果を保存
        for i in range(5):
            result = BenchmarkResult(
                platform="Linux",
                cpu_info="Test CPU",
                processing_time={"test": 1.0},
                accuracy_score={"test": 0.9},
                memory_usage=100.0,
                thread_config={},
                ocr_settings={},
                timestamp=f"2025-01-0{i+1}T12:00:00",
                errors={}
            )
            self.manager.save_result(result)

        # 3つまで保持
        deleted_count = self.manager.cleanup_old_results(keep_count=3)
        self.assertEqual(deleted_count, 2)

        # 残った結果を確認
        remaining_results = self.manager.load_results()
        self.assertEqual(len(remaining_results), 3)


class TestUtilityFunctions(unittest.TestCase):
    """ユーティリティ関数のテスト."""

    def test_calculate_text_similarity(self):
        """テキスト類似度計算のテスト."""
        # 完全一致
        similarity = calculate_text_similarity("hello", "hello")
        self.assertEqual(similarity, 1.0)

        # 部分一致
        similarity = calculate_text_similarity("hello", "helo")
        self.assertGreater(similarity, 0.5)

        # 完全不一致
        similarity = calculate_text_similarity("hello", "world")
        self.assertLess(similarity, 0.5)

        # 空文字列
        similarity = calculate_text_similarity("", "")
        self.assertEqual(similarity, 1.0)

        similarity = calculate_text_similarity("hello", "")
        self.assertEqual(similarity, 0.0)

    @patch('app.core.benchmark.PSUTIL_AVAILABLE', True)
    @patch('app.core.benchmark.psutil')
    def test_get_memory_usage(self, mock_psutil):
        """メモリ使用量取得のテスト."""
        # モック設定
        mock_process_instance = Mock()
        mock_memory_info = Mock()
        mock_memory_info.rss = 1024 * 1024 * 100  # 100MB
        mock_process_instance.memory_info.return_value = mock_memory_info
        mock_psutil.Process.return_value = mock_process_instance

        memory_usage = get_memory_usage()
        self.assertEqual(memory_usage, 100.0)  # 100MB

    def test_get_memory_usage_no_psutil(self):
        """psutil未インストール時のメモリ使用量取得テスト."""
        with patch('app.core.benchmark.PSUTIL_AVAILABLE', False):
            memory_usage = get_memory_usage()
            self.assertEqual(memory_usage, 0.0)

    @patch('app.core.benchmark.os.cpu_count')
    @patch('app.core.benchmark.platform.processor')
    def test_get_cpu_info_fallback(self, mock_processor, mock_cpu_count):
        """CPU情報取得（フォールバック）のテスト."""
        mock_processor.return_value = "Test Processor"
        mock_cpu_count.return_value = 8

        with patch.dict('sys.modules', {'app.core.cpu_profiler': None}):
            cpu_info = get_cpu_info()
            self.assertIn("Test Processor", cpu_info)
            self.assertIn("8", cpu_info)

    @patch.dict('os.environ', {
        'OMP_NUM_THREADS': '4',
        'OPENBLAS_NUM_THREADS': '2',
        'MKL_NUM_THREADS': '6'
    })
    def test_get_current_thread_config(self):
        """現在のスレッド設定取得のテスト."""
        config = get_current_thread_config()
        self.assertEqual(config['OMP_NUM_THREADS'], '4')
        self.assertEqual(config['OPENBLAS_NUM_THREADS'], '2')
        self.assertEqual(config['MKL_NUM_THREADS'], '6')


class TestComprehensiveAnalysis(unittest.TestCase):
    """包括分析機能のテスト."""

    @patch('app.core.benchmark.BenchmarkManager')
    @patch('app.core.benchmark.OCRBenchmark')
    def test_run_comprehensive_analysis(self, mock_benchmark_class, mock_manager_class):
        """包括分析実行のテスト."""
        # モック設定
        mock_result = BenchmarkResult(
            platform="Linux",
            cpu_info="Test CPU",
            processing_time={"test": 1.0},
            accuracy_score={"test": 0.9},
            memory_usage=100.0,
            thread_config={},
            ocr_settings={},
            timestamp="2025-01-01T12:00:00",
            errors={}
        )

        mock_benchmark = Mock()
        mock_benchmark.run_full_benchmark.return_value = mock_result
        mock_benchmark_class.return_value = mock_benchmark

        mock_manager = Mock()
        mock_manager.save_result.return_value = Path("/test/path")
        mock_manager_class.return_value = mock_manager

        mock_ocr_engine = Mock()

        # 包括分析実行
        analysis_result = run_comprehensive_analysis(mock_ocr_engine)

        # 結果検証
        self.assertIn("result", analysis_result)
        self.assertIn("comparison", analysis_result)
        self.assertIn("issues", analysis_result)
        self.assertIn("text_report", analysis_result)
        self.assertIn("saved_path", analysis_result)

        self.assertIsInstance(analysis_result["result"], BenchmarkResult)
        self.assertIsInstance(analysis_result["text_report"], str)


if __name__ == '__main__':
    unittest.main()