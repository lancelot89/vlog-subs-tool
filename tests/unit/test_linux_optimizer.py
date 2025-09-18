"""Linux性能最適化システムのテスト."""

import os
import platform
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from app.core.linux_optimizer import (
    CPUDetector,
    CPUInfo,
    CPUSpecificOptimizer,
    IOOptimizer,
    MemoryOptimizer,
    NUMADetector,
    NUMAOptimizer,
    NUMATopology,
    OpenBLASOptimizer,
    apply_comprehensive_linux_optimization,
    apply_cpu_optimization,
    apply_io_optimization,
    apply_memory_optimization,
    apply_numa_optimization,
    apply_openblas_optimization,
)


class TestNUMATopology(unittest.TestCase):
    """NUMATopologyクラスのテスト."""

    def test_numa_topology_creation(self):
        """NUMA構成の基本的な作成をテスト."""
        topology = NUMATopology(
            nodes=2,
            cores_per_node=[8, 8],
            memory_per_node=[16, 16],
            node_distances={(0, 0): 10, (0, 1): 21, (1, 0): 21, (1, 1): 10},
            cpu_list_per_node={0: [0, 1, 2, 3, 4, 5, 6, 7], 1: [8, 9, 10, 11, 12, 13, 14, 15]}
        )

        self.assertEqual(topology.nodes, 2)
        self.assertTrue(topology.is_numa_system())
        self.assertEqual(len(topology.cores_per_node), 2)

    def test_non_numa_system(self):
        """非NUMA環境のテスト."""
        topology = NUMATopology(
            nodes=1,
            cores_per_node=[8],
            memory_per_node=[16],
            node_distances={(0, 0): 10},
            cpu_list_per_node={0: [0, 1, 2, 3, 4, 5, 6, 7]}
        )

        self.assertFalse(topology.is_numa_system())

    def test_optimal_cpu_set_numa(self):
        """NUMA環境での最適CPU配置をテスト."""
        topology = NUMATopology(
            nodes=2,
            cores_per_node=[4, 4],
            memory_per_node=[8, 8],
            node_distances={(0, 0): 10, (0, 1): 21, (1, 0): 21, (1, 1): 10},
            cpu_list_per_node={0: [0, 1, 2, 3], 1: [4, 5, 6, 7]}
        )

        # 6スレッド要求時は最初のノードから4つ、次のノードから2つ
        optimal_cpus = topology.get_optimal_cpu_set(6)
        self.assertEqual(optimal_cpus, [0, 1, 2, 3, 4, 5])

    def test_optimal_cpu_set_non_numa(self):
        """非NUMA環境での最適CPU配置をテスト."""
        topology = NUMATopology(
            nodes=1,
            cores_per_node=[8],
            memory_per_node=[16],
            node_distances={(0, 0): 10},
            cpu_list_per_node={0: [0, 1, 2, 3, 4, 5, 6, 7]}
        )

        optimal_cpus = topology.get_optimal_cpu_set(4)
        self.assertEqual(optimal_cpus, [0, 1, 2, 3])


class TestCPUInfo(unittest.TestCase):
    """CPUInfoクラスのテスト."""

    def test_cpu_info_creation(self):
        """CPU情報の基本的な作成をテスト."""
        cpu_info = CPUInfo(
            vendor="Intel",
            model="Intel Core i7-10700K",
            architecture="x86_64",
            cores=8,
            threads=16,
            generation=10,
            features=["avx2", "sse4_1"],
            frequency=3.8,
            cache_sizes={"L1d": 32, "L2": 256, "L3": 16384}
        )

        self.assertEqual(cpu_info.vendor, "Intel")
        self.assertEqual(cpu_info.generation, 10)
        self.assertFalse(cpu_info.is_high_core_count())  # 8コアは境界値で高コア数ではない
        self.assertFalse(cpu_info.is_server_cpu())

    def test_high_core_count_cpu(self):
        """高コア数CPUの判定をテスト."""
        high_core_cpu = CPUInfo(
            vendor="Intel",
            model="Intel Core i9-12900K",
            architecture="x86_64",
            cores=16,  # 8コアより多い
            threads=24,
            generation=12,
            features=["avx2", "sse4_1"],
            frequency=3.2,
            cache_sizes={"L1d": 48, "L2": 512, "L3": 30720}
        )

        self.assertTrue(high_core_cpu.is_high_core_count())

    def test_server_cpu_detection(self):
        """サーバーCPUの検出をテスト."""
        # Intel Xeon
        xeon_cpu = CPUInfo(
            vendor="Intel", model="Intel Xeon E5-2680 v4", architecture="x86_64",
            cores=14, threads=28, generation=None, features=[], frequency=2.4, cache_sizes={}
        )
        self.assertTrue(xeon_cpu.is_server_cpu())

        # AMD EPYC
        epyc_cpu = CPUInfo(
            vendor="AMD", model="AMD EPYC 7742", architecture="x86_64",
            cores=64, threads=128, generation=2, features=[], frequency=2.25, cache_sizes={}
        )
        self.assertTrue(epyc_cpu.is_server_cpu())

        # 通常のCPU
        normal_cpu = CPUInfo(
            vendor="Intel", model="Intel Core i5-9400", architecture="x86_64",
            cores=6, threads=6, generation=9, features=[], frequency=2.9, cache_sizes={}
        )
        self.assertFalse(normal_cpu.is_server_cpu())


class TestNUMADetector(unittest.TestCase):
    """NUMADetectorクラスのテスト."""

    def setUp(self):
        self.detector = NUMADetector()

    @patch('pathlib.Path.exists')
    def test_numa_not_available(self, mock_exists):
        """NUMA非対応環境のテスト."""
        mock_exists.return_value = False
        result = self.detector.detect_numa_topology()
        self.assertIsNone(result)

    def test_parse_cpu_list(self):
        """CPU一覧文字列のパースをテスト."""
        # 基本的なケース
        result = self.detector._parse_cpu_list("0-3")
        self.assertEqual(result, [0, 1, 2, 3])

        # 複数範囲のケース
        result = self.detector._parse_cpu_list("0-3,8-11")
        self.assertEqual(result, [0, 1, 2, 3, 8, 9, 10, 11])

        # 単一CPU
        result = self.detector._parse_cpu_list("0")
        self.assertEqual(result, [0])

        # 混合
        result = self.detector._parse_cpu_list("0,2-4,7")
        self.assertEqual(result, [0, 2, 3, 4, 7])


class TestCPUDetector(unittest.TestCase):
    """CPUDetectorクラスのテスト."""

    def setUp(self):
        self.detector = CPUDetector()

    def test_parse_vendor(self):
        """ベンダー解析のテスト."""
        self.assertEqual(self.detector._parse_vendor("GenuineIntel", "Intel Core i7"), "Intel")
        self.assertEqual(self.detector._parse_vendor("AuthenticAMD", "AMD Ryzen 5"), "AMD")
        self.assertEqual(self.detector._parse_vendor("", "Apple M1"), "Apple")
        self.assertEqual(self.detector._parse_vendor("Unknown", "Unknown CPU"), "Unknown")

    def test_extract_generation_intel(self):
        """Intel CPU世代抽出のテスト."""
        # 標準命名規則
        gen = self.detector._extract_generation("Intel Core i7-10700K", "Intel")
        self.assertEqual(gen, 10)

        gen = self.detector._extract_generation("Intel Core i5-11400", "Intel")
        self.assertEqual(gen, 11)

        # 新命名規則
        gen = self.detector._extract_generation("12th Gen Intel Core i7-12700K", "Intel")
        self.assertEqual(gen, 12)

    def test_extract_generation_amd(self):
        """AMD CPU世代抽出のテスト."""
        # Zen 2
        gen = self.detector._extract_generation("AMD Ryzen 7 3700X", "AMD")
        self.assertEqual(gen, 2)

        # Zen 3
        gen = self.detector._extract_generation("AMD Ryzen 9 5900X", "AMD")
        self.assertEqual(gen, 3)

        # Zen 4
        gen = self.detector._extract_generation("AMD Ryzen 7 7700X", "AMD")
        self.assertEqual(gen, 4)

    def test_get_core_thread_count(self):
        """コア数・スレッド数計算のテスト."""
        # モックcpuinfoコンテンツ
        cpuinfo_content = """
processor	: 0
physical id	: 0
core id		: 0
cpu cores	: 4

processor	: 1
physical id	: 0
core id		: 1

processor	: 2
physical id	: 0
core id		: 2

processor	: 3
physical id	: 0
core id		: 3

processor	: 4
physical id	: 0
core id		: 0

processor	: 5
physical id	: 0
core id		: 1

processor	: 6
physical id	: 0
core id		: 2

processor	: 7
physical id	: 0
core id		: 3
"""
        cores, threads = self.detector._get_core_thread_count(cpuinfo_content)
        self.assertEqual(cores, 4)  # 4つの物理コア
        self.assertEqual(threads, 8)  # 8つの論理プロセッサ


class TestNUMAOptimizer(unittest.TestCase):
    """NUMAOptimizerクラスのテスト."""

    def test_non_numa_optimization(self):
        """非NUMA環境の最適化をテスト."""
        optimizer = NUMAOptimizer(numa_topology=None)
        env_vars = optimizer.optimize_for_numa()

        self.assertIn("OMP_PLACES", env_vars)
        self.assertIn("OMP_PROC_BIND", env_vars)
        self.assertEqual(env_vars["OMP_PLACES"], "cores")
        self.assertEqual(env_vars["OMP_PROC_BIND"], "close")

    def test_numa_optimization(self):
        """NUMA環境の最適化をテスト."""
        numa_topology = NUMATopology(
            nodes=2,
            cores_per_node=[4, 4],
            memory_per_node=[8, 8],
            node_distances={(0, 0): 10, (0, 1): 21, (1, 0): 21, (1, 1): 10},
            cpu_list_per_node={0: [0, 1, 2, 3], 1: [4, 5, 6, 7]}
        )

        optimizer = NUMAOptimizer(numa_topology=numa_topology)
        env_vars = optimizer.optimize_for_numa()

        self.assertIn("OMP_PLACES", env_vars)
        self.assertIn("OMP_PROC_BIND", env_vars)
        self.assertEqual(env_vars["OMP_PROC_BIND"], "spread")

    def test_numa_memory_policy(self):
        """NUMAメモリポリシーのテスト."""
        numa_topology = NUMATopology(
            nodes=2,
            cores_per_node=[4, 4],
            memory_per_node=[8, 8],
            node_distances={(0, 0): 10, (0, 1): 21, (1, 0): 21, (1, 1): 10},
            cpu_list_per_node={0: [0, 1, 2, 3], 1: [4, 5, 6, 7]}
        )

        optimizer = NUMAOptimizer(numa_topology=numa_topology)
        memory_vars = optimizer.get_numa_memory_policy()

        self.assertIn("NUMA_POLICY", memory_vars)
        self.assertIn("NUMA_PREFERRED_NODE", memory_vars)


class TestCPUSpecificOptimizer(unittest.TestCase):
    """CPUSpecificOptimizerクラスのテスト."""

    def test_intel_server_cpu_optimization(self):
        """Intel サーバーCPU最適化のテスト."""
        cpu_info = CPUInfo(
            vendor="Intel", model="Intel Xeon E5-2680 v4", architecture="x86_64",
            cores=14, threads=28, generation=None, features=["avx2"], frequency=2.4, cache_sizes={}
        )

        optimizer = CPUSpecificOptimizer(cpu_info=cpu_info)
        env_vars = optimizer.optimize_for_intel()

        self.assertIn("MKL_NUM_THREADS", env_vars)
        self.assertIn("MKL_DYNAMIC", env_vars)
        self.assertEqual(env_vars["MKL_DYNAMIC"], "TRUE")

    def test_intel_modern_cpu_optimization(self):
        """Intel 新世代CPU最適化のテスト."""
        cpu_info = CPUInfo(
            vendor="Intel", model="Intel Core i7-10700K", architecture="x86_64",
            cores=8, threads=16, generation=10, features=["avx2"], frequency=3.8, cache_sizes={}
        )

        optimizer = CPUSpecificOptimizer(cpu_info=cpu_info)
        env_vars = optimizer.optimize_for_intel()

        self.assertIn("MKL_NUM_THREADS", env_vars)
        self.assertIn("MKL_ENABLE_INSTRUCTIONS", env_vars)
        self.assertEqual(env_vars["MKL_ENABLE_INSTRUCTIONS"], "AVX2")

    def test_amd_ryzen_optimization(self):
        """AMD Ryzen最適化のテスト."""
        cpu_info = CPUInfo(
            vendor="AMD", model="AMD Ryzen 7 3700X", architecture="x86_64",
            cores=8, threads=16, generation=2, features=["avx2"], frequency=3.6, cache_sizes={}
        )

        optimizer = CPUSpecificOptimizer(cpu_info=cpu_info)
        env_vars = optimizer.optimize_for_amd()

        self.assertIn("OPENBLAS_CORETYPE", env_vars)
        self.assertEqual(env_vars["OPENBLAS_CORETYPE"], "RYZEN")

    def test_amd_epyc_optimization(self):
        """AMD EPYC最適化のテスト."""
        cpu_info = CPUInfo(
            vendor="AMD", model="AMD EPYC 7742", architecture="x86_64",
            cores=64, threads=128, generation=2, features=["avx2"], frequency=2.25, cache_sizes={}
        )

        optimizer = CPUSpecificOptimizer(cpu_info=cpu_info)
        env_vars = optimizer.optimize_for_amd()

        self.assertIn("OPENBLAS_CORETYPE", env_vars)
        self.assertEqual(env_vars["OPENBLAS_CORETYPE"], "EPYC")

    def test_ccx_optimal_threads_calculation(self):
        """Ryzen CCX最適スレッド数計算のテスト."""
        # Zen 3 (8コア)
        cpu_info = CPUInfo(
            vendor="AMD", model="AMD Ryzen 7 5800X", architecture="x86_64",
            cores=8, threads=16, generation=3, features=[], frequency=3.8, cache_sizes={}
        )
        optimizer = CPUSpecificOptimizer(cpu_info=cpu_info)
        threads = optimizer._calculate_ccx_optimal_threads()
        self.assertEqual(threads, 8)

        # Zen 2 (6コア)
        cpu_info.generation = 2
        cpu_info.cores = 6
        threads = optimizer._calculate_ccx_optimal_threads()
        self.assertEqual(threads, 4)  # 1CCX優先


class TestOpenBLASOptimizer(unittest.TestCase):
    """OpenBLASOptimizerクラスのテスト."""

    def setUp(self):
        self.cpu_info = CPUInfo(
            vendor="Intel", model="Intel Core i7-10700K", architecture="x86_64",
            cores=8, threads=16, generation=10, features=["avx2"], frequency=3.8, cache_sizes={}
        )

    @patch('app.core.linux_optimizer.OpenBLASOptimizer._is_ubuntu_like')
    def test_non_ubuntu_environment(self, mock_is_ubuntu):
        """非Ubuntu環境でのバリアント選択をテスト."""
        mock_is_ubuntu.return_value = False

        optimizer = OpenBLASOptimizer(cpu_info=self.cpu_info)
        variant = optimizer.select_optimal_openblas_variant()

        self.assertEqual(variant, "default")

    def test_configure_openblas_environment(self):
        """OpenBLAS環境設定のテスト."""
        optimizer = OpenBLASOptimizer(cpu_info=self.cpu_info)
        env_vars = optimizer.configure_openblas_environment()

        self.assertIn("OPENBLAS_NUM_THREADS", env_vars)
        self.assertIn("OPENBLAS_CORETYPE", env_vars)

    def test_amd_cpu_openblas_config(self):
        """AMD CPU向けOpenBLAS設定のテスト."""
        amd_cpu = CPUInfo(
            vendor="AMD", model="AMD Ryzen 7 3700X", architecture="x86_64",
            cores=8, threads=16, generation=2, features=["avx2"], frequency=3.6, cache_sizes={}
        )

        optimizer = OpenBLASOptimizer(cpu_info=amd_cpu)
        env_vars = optimizer.configure_openblas_environment()

        self.assertEqual(env_vars["OPENBLAS_CORETYPE"], "RYZEN")


class TestMemoryOptimizer(unittest.TestCase):
    """MemoryOptimizerクラスのテスト."""

    def setUp(self):
        self.optimizer = MemoryOptimizer()

    def test_memory_allocation_optimization(self):
        """メモリアロケーション最適化のテスト."""
        env_vars = self.optimizer.optimize_memory_allocation()

        self.assertIn("MALLOC_MMAP_THRESHOLD_", env_vars)
        self.assertIn("MALLOC_TRIM_THRESHOLD_", env_vars)
        self.assertEqual(env_vars["MALLOC_MMAP_THRESHOLD_"], "65536")

    @patch('builtins.open', mock_open(read_data="MemTotal:       16777216 kB\n"))
    def test_paddle_memory_configuration(self):
        """PaddleOCRメモリ設定のテスト."""
        env_vars = self.optimizer.configure_paddle_memory()

        self.assertIn("FLAGS_fraction_of_cpu_memory_to_use", env_vars)
        self.assertIn("FLAGS_allocator_strategy", env_vars)
        self.assertEqual(env_vars["FLAGS_allocator_strategy"], "auto_growth")

    @patch('pathlib.Path.exists')
    def test_thp_support_detection(self, mock_exists):
        """THP（Transparent Huge Pages）サポート検出のテスト."""
        mock_exists.return_value = True
        self.assertTrue(self.optimizer._supports_thp())

        mock_exists.return_value = False
        self.assertFalse(self.optimizer._supports_thp())

    @patch('builtins.open', mock_open(read_data="MemTotal:       33554432 kB\n"))
    def test_get_total_memory_gb(self):
        """総メモリ量取得のテスト."""
        memory_gb = self.optimizer._get_total_memory_gb()
        self.assertEqual(memory_gb, 32)  # 33554432 KB = 32 GB


class TestIOOptimizer(unittest.TestCase):
    """IOOptimizerクラスのテスト."""

    def setUp(self):
        self.optimizer = IOOptimizer()

    @patch('pathlib.Path.glob')
    @patch('pathlib.Path.iterdir')
    def test_ssd_detection(self, mock_iterdir, mock_glob):
        """SSD検出のテスト."""
        # NVMe検出のモック
        mock_glob.return_value = [Path("/dev/nvme0n1")]
        self.assertTrue(self.optimizer._detect_ssd())

        # 回転数による検出のモック
        mock_glob.return_value = []

        mock_device = MagicMock()
        mock_device.name = "sda"
        mock_rotational_file = mock_device / "queue" / "rotational"
        mock_rotational_file.exists.return_value = True
        mock_rotational_file.read_text.return_value = "0"  # SSD

        mock_iterdir.return_value = [mock_device]

        self.assertTrue(self.optimizer._detect_ssd())

    def test_model_loading_optimization_ssd(self):
        """SSD環境でのモデル読み込み最適化をテスト."""
        with patch.object(self.optimizer, '_detect_ssd', return_value=True):
            env_vars = self.optimizer.optimize_model_loading()

            self.assertEqual(env_vars["PADDLE_MODEL_IO_STRATEGY"], "mmap")
            self.assertIn("PYTHONUNBUFFERED", env_vars)

    def test_model_loading_optimization_hdd(self):
        """HDD環境でのモデル読み込み最適化をテスト."""
        with patch.object(self.optimizer, '_detect_ssd', return_value=False):
            env_vars = self.optimizer.optimize_model_loading()

            self.assertEqual(env_vars["PADDLE_MODEL_IO_STRATEGY"], "sequential")
            self.assertIn("PYTHONIOENCODING", env_vars)

    @patch('pathlib.Path.exists')
    def test_model_cache_optimization(self, mock_exists):
        """モデルキャッシュ最適化のテスト."""
        mock_exists.return_value = True

        env_vars = self.optimizer.setup_model_cache_optimization()

        self.assertIn("PADDLE_CACHE_HINT", env_vars)
        self.assertIn("PADDLE_USE_FILESYSTEM_CACHE", env_vars)


class TestLinuxOptimizerIntegration(unittest.TestCase):
    """Linux最適化システムの統合テスト."""

    def setUp(self):
        # 元の環境変数を保存
        self.original_env = os.environ.copy()

    def tearDown(self):
        # 環境変数を復元
        os.environ.clear()
        os.environ.update(self.original_env)

    @patch('platform.system')
    def test_non_linux_environment(self, mock_platform):
        """Linux以外の環境での最適化スキップをテスト."""
        mock_platform.return_value = "Windows"

        result = apply_comprehensive_linux_optimization()

        self.assertEqual(result, {})

    @patch('platform.system')
    def test_comprehensive_optimization_application(self, mock_platform):
        """包括的最適化の適用をテスト."""
        mock_platform.return_value = "Linux"

        # 元の環境変数数を記録
        original_env_count = len(os.environ)

        result = apply_comprehensive_linux_optimization()

        # 結果の構造確認
        expected_categories = ["numa", "cpu", "openblas", "memory", "io"]
        for category in expected_categories:
            self.assertIn(category, result)

        # 環境変数が実際に設定されていることを確認
        self.assertGreater(len(os.environ), original_env_count)

    def test_individual_optimization_functions(self):
        """個別最適化関数のテスト."""
        # NUMA最適化
        numa_result = apply_numa_optimization()
        self.assertIsInstance(numa_result, dict)

        # CPU最適化
        cpu_result = apply_cpu_optimization()
        self.assertIsInstance(cpu_result, dict)

        # OpenBLAS最適化
        openblas_result = apply_openblas_optimization()
        self.assertIsInstance(openblas_result, dict)

        # メモリ最適化
        memory_result = apply_memory_optimization()
        self.assertIsInstance(memory_result, dict)

        # I/O最適化
        io_result = apply_io_optimization()
        self.assertIsInstance(io_result, dict)

    def test_environment_variable_persistence(self):
        """環境変数の永続化をテスト."""
        # 特定の環境変数を設定
        apply_numa_optimization()

        # 設定された環境変数が存在することを確認
        numa_vars = ["OMP_PLACES", "OMP_PROC_BIND"]
        for var in numa_vars:
            if var in os.environ:
                self.assertIsNotNone(os.environ[var])

    @patch('app.core.linux_optimizer.CPUDetector.detect_cpu_info')
    def test_optimization_with_specific_cpu(self, mock_detect_cpu):
        """特定CPU構成での最適化をテスト."""
        # Intel 新世代CPUをモック
        mock_cpu_info = CPUInfo(
            vendor="Intel", model="Intel Core i7-12700K", architecture="x86_64",
            cores=12, threads=20, generation=12, features=["avx2", "avx512f"],
            frequency=3.6, cache_sizes={"L1d": 48, "L2": 512, "L3": 25600}
        )
        mock_detect_cpu.return_value = mock_cpu_info

        cpu_result = apply_cpu_optimization()

        # Intel特有の設定が適用されていることを確認
        self.assertIn("MKL_NUM_THREADS", cpu_result)
        self.assertIn("INTEL_NUM_THREADS", cpu_result)

    def test_error_handling_in_optimization(self):
        """最適化中のエラーハンドリングをテスト."""
        # 無効なCPU情報での最適化
        invalid_cpu = CPUInfo(
            vendor="Unknown", model="Unknown CPU", architecture="unknown",
            cores=0, threads=0, generation=None, features=[], frequency=0.0, cache_sizes={}
        )

        optimizer = CPUSpecificOptimizer(cpu_info=invalid_cpu)
        result = optimizer.apply_cpu_optimization()

        # エラーが発生してもフォールバック設定が返されることを確認
        self.assertIsInstance(result, dict)
        self.assertIn("OMP_NUM_THREADS", result)


if __name__ == '__main__':
    unittest.main()