"""Unit tests for the CPU profiler and adaptive thread configuration system.

Tests the cross-platform CPU detection, thread optimization, and configuration
caching functionality added for Issue #130 - CPU performance-based adaptive
thread configuration system.
"""

import json
import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from app.core.cpu_profiler import (
    CPUProfile,
    ThreadConfig,
    CPUProfiler,
    ThreadConfigManager,
    get_adaptive_thread_config
)


class TestCPUProfile(unittest.TestCase):
    """Test CPUProfile dataclass functionality."""

    def test_cpu_profile_creation(self):
        """Test CPUProfile creation and signature generation."""
        profile = CPUProfile(
            architecture="x86_64",
            vendor="Intel",
            cores_physical=8,
            cores_logical=16,
            generation=10,
            features=["AVX2", "SSE4.2"],
            name="Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz",
            platform_name="Windows"
        )

        self.assertEqual(profile.architecture, "x86_64")
        self.assertEqual(profile.vendor, "Intel")
        self.assertEqual(profile.cores_physical, 8)
        self.assertEqual(profile.cores_logical, 16)
        self.assertEqual(profile.generation, 10)
        self.assertEqual(profile.features, ["AVX2", "SSE4.2"])
        self.assertEqual(profile.platform_name, "Windows")

        # Test signature generation
        expected_signature = "Windows_Intel_x86_64_10_8_16"
        self.assertEqual(profile.signature(), expected_signature)

    def test_cpu_profile_with_none_generation(self):
        """Test CPUProfile with None generation."""
        profile = CPUProfile(
            architecture="arm64",
            vendor="Unknown",
            cores_physical=4,
            cores_logical=4,
            generation=None,
            features=[],
            name="Unknown CPU",
            platform_name="Linux"
        )

        expected_signature = "Linux_Unknown_arm64_None_4_4"
        self.assertEqual(profile.signature(), expected_signature)


class TestThreadConfig(unittest.TestCase):
    """Test ThreadConfig dataclass functionality."""

    def test_thread_config_basic(self):
        """Test basic ThreadConfig functionality."""
        config = ThreadConfig(
            omp_threads=4,
            openblas_threads=4,
            mkl_threads=4
        )

        env_vars = config.to_env_vars()
        expected = {
            "OMP_NUM_THREADS": "4",
            "OPENBLAS_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "4"
        }

        self.assertEqual(env_vars["OMP_NUM_THREADS"], expected["OMP_NUM_THREADS"])
        self.assertEqual(env_vars["OPENBLAS_NUM_THREADS"], expected["OPENBLAS_NUM_THREADS"])
        self.assertEqual(env_vars["MKL_NUM_THREADS"], expected["MKL_NUM_THREADS"])

    def test_thread_config_apple_silicon(self):
        """Test ThreadConfig for Apple Silicon."""
        config = ThreadConfig(
            omp_threads=8,
            openblas_threads=1,
            veclib_threads=8
        )

        env_vars = config.to_env_vars()
        self.assertEqual(env_vars["OMP_NUM_THREADS"], "8")
        self.assertEqual(env_vars["OPENBLAS_NUM_THREADS"], "1")
        self.assertEqual(env_vars["VECLIB_MAXIMUM_THREADS"], "8")

    def test_thread_config_amd_ryzen(self):
        """Test ThreadConfig for AMD Ryzen."""
        config = ThreadConfig(
            omp_threads=6,
            openblas_threads=6,
            openblas_coretype="RYZEN"
        )

        env_vars = config.to_env_vars()
        self.assertEqual(env_vars["OMP_NUM_THREADS"], "6")
        self.assertEqual(env_vars["OPENBLAS_NUM_THREADS"], "6")
        self.assertEqual(env_vars["OPENBLAS_CORETYPE"], "RYZEN")


class TestCPUProfiler(unittest.TestCase):
    """Test CPUProfiler CPU detection functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.profiler = CPUProfiler()

    @patch('app.core.cpu_profiler.subprocess.run')
    @patch('app.core.cpu_profiler.platform.system')
    @patch('app.core.cpu_profiler.platform.machine')
    def test_detect_windows_cpu(self, mock_machine, mock_system, mock_subprocess):
        """Test Windows CPU detection."""
        mock_system.return_value = "Windows"
        mock_machine.return_value = "AMD64"

        # Also need to mock the instance variable
        self.profiler.machine = "AMD64"

        # Mock wmic output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Node,Name,NumberOfCores,NumberOfLogicalProcessors
DESKTOP,Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz,8,16
"""
        mock_subprocess.return_value = mock_result

        profile = self.profiler._detect_windows_cpu()

        self.assertEqual(profile.architecture, "amd64".lower())
        self.assertEqual(profile.vendor, "Intel")
        self.assertEqual(profile.cores_physical, 8)
        self.assertEqual(profile.cores_logical, 16)
        self.assertEqual(profile.generation, 10)
        self.assertEqual(profile.name, "Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz")
        self.assertEqual(profile.platform_name, "Windows")

    @patch('app.core.cpu_profiler.subprocess.run')
    @patch('app.core.cpu_profiler.platform.system')
    @patch('app.core.cpu_profiler.platform.machine')
    def test_detect_macos_cpu(self, mock_machine, mock_system, mock_subprocess):
        """Test macOS CPU detection."""
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "arm64"

        # Also need to mock the instance variable
        self.profiler.machine = "arm64"

        # Mock sysctl outputs
        def sysctl_side_effect(cmd, **kwargs):
            if "machdep.cpu.brand_string" in cmd:
                result = Mock()
                result.returncode = 0
                result.stdout = "Apple M2 Pro"
                return result
            elif "hw.physicalcpu" in cmd:
                result = Mock()
                result.returncode = 0
                result.stdout = "10"
                return result
            elif "hw.logicalcpu" in cmd:
                result = Mock()
                result.returncode = 0
                result.stdout = "10"
                return result
            else:
                result = Mock()
                result.returncode = 1
                return result

        mock_subprocess.side_effect = sysctl_side_effect

        profile = self.profiler._detect_macos_cpu()

        self.assertEqual(profile.architecture, "arm64")
        self.assertEqual(profile.vendor, "Apple")
        self.assertEqual(profile.cores_physical, 10)
        self.assertEqual(profile.cores_logical, 10)
        self.assertEqual(profile.generation, 2)  # M2
        self.assertEqual(profile.name, "Apple M2 Pro")
        self.assertEqual(profile.platform_name, "Darwin")

    @patch('builtins.open', new_callable=mock_open)
    @patch('app.core.cpu_profiler.platform.system')
    @patch('app.core.cpu_profiler.platform.machine')
    def test_detect_linux_cpu(self, mock_machine, mock_system, mock_file):
        """Test Linux CPU detection."""
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"

        # Also need to mock the instance variable
        self.profiler.machine = "x86_64"

        # Mock /proc/cpuinfo content
        cpuinfo_content = """processor	: 0
model name	: AMD Ryzen 5 3600 6-Core Processor
processor	: 1
model name	: AMD Ryzen 5 3600 6-Core Processor
processor	: 2
model name	: AMD Ryzen 5 3600 6-Core Processor
core id		: 0
core id		: 1
core id		: 2
flags		: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush mmx fxsr sse sse2 ht syscall nx mmxext fxsr_opt pdpe1gb rdtscp lm constant_tsc rep_good nopl nonstop_tsc cpuid extd_apicid aperfmperf pni pclmulqdq monitor ssse3 fma cx16 sse4_1 sse4_2 movbe popcnt aes xsave avx f16c rdrand lahf_lm cmp_legacy svm extapic cr8_legacy abm sse4a misalignsse 3dnowprefetch osvw ibs skinit wdt tce topoext perfctr_core perfctr_nb bpext perfctr_llc mwaitx cpb cat_l3 cdp_l3 hw_pstate sme ssbd mba sev ibrs ibpb stibp vmmcall fsgsbase bmi1 avx2 smep bmi2 cqm rdt_a rdseed adx smap clflushopt clwb sha_ni xsaveopt xsavec xgetbv1 xsaves cqm_llc cqm_occup_llc cqm_mbm_total cqm_mbm_local clzero irperf xsaveerptr rdpru wbnoinvd arat npt lbrv svm_lock nrip_save tsc_scale vmcb_clean flushbyasid decodeassists pausefilter pfthreshold avic v_vmsave_vmload vgif umip rdpid overflow_recov succor smca
"""
        mock_file.return_value.read.return_value = cpuinfo_content

        profile = self.profiler._detect_linux_cpu()

        self.assertEqual(profile.architecture, "x86_64")
        self.assertEqual(profile.vendor, "AMD")
        self.assertEqual(profile.cores_physical, 3)  # 3 unique core IDs
        self.assertEqual(profile.cores_logical, 3)   # 3 processors
        self.assertEqual(profile.generation, 2)      # Ryzen 3xxx = Zen 2
        self.assertEqual(profile.name, "AMD Ryzen 5 3600 6-Core Processor")
        self.assertEqual(profile.platform_name, "Linux")
        self.assertIn("AVX2", profile.features)
        self.assertIn("SSE4.2", profile.features)

    def test_extract_vendor(self):
        """Test CPU vendor extraction."""
        test_cases = [
            ("Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz", "Intel"),
            ("AMD Ryzen 5 3600 6-Core Processor", "AMD"),
            ("Apple M2 Pro", "Apple"),
            ("Unknown Processor", "Unknown"),
        ]

        for cpu_name, expected_vendor in test_cases:
            with self.subTest(cpu_name=cpu_name):
                result = self.profiler._extract_vendor(cpu_name)
                self.assertEqual(result, expected_vendor)

    def test_extract_generation_intel(self):
        """Test Intel CPU generation extraction."""
        test_cases = [
            ("Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz", 10),
            ("Intel(R) Core(TM) i5-11400 CPU @ 2.60GHz", 11),
            ("12th Gen Intel(R) Core(TM) i9-12900K", 12),
            ("Intel(R) Core(TM) i3-8100 CPU @ 3.60GHz", 8),
            ("Intel(R) Pentium(R) CPU G4560 @ 3.50GHz", None),  # Not Core series
        ]

        for cpu_name, expected_gen in test_cases:
            with self.subTest(cpu_name=cpu_name):
                result = self.profiler._extract_generation(cpu_name, "Intel")
                self.assertEqual(result, expected_gen)

    def test_extract_generation_amd(self):
        """Test AMD CPU generation extraction."""
        test_cases = [
            ("AMD Ryzen 5 3600 6-Core Processor", 2),    # Zen 2
            ("AMD Ryzen 7 5800X 8-Core Processor", 3),   # Zen 3
            ("AMD Ryzen 5 2600 Six-Core Processor", 1),  # Zen+
            ("AMD FX-8350 Eight-Core Processor", None),  # Not Ryzen
        ]

        for cpu_name, expected_gen in test_cases:
            with self.subTest(cpu_name=cpu_name):
                result = self.profiler._extract_generation(cpu_name, "AMD")
                self.assertEqual(result, expected_gen)

    def test_extract_generation_apple(self):
        """Test Apple CPU generation extraction."""
        test_cases = [
            ("Apple M1", 1),
            ("Apple M2 Pro", 2),
            ("Apple M3 Max", 3),
            ("Apple A15 Bionic", None),  # Not M series
        ]

        for cpu_name, expected_gen in test_cases:
            with self.subTest(cpu_name=cpu_name):
                result = self.profiler._extract_generation(cpu_name, "Apple")
                self.assertEqual(result, expected_gen)

    @patch('app.core.cpu_profiler.os.cpu_count')
    @patch('app.core.cpu_profiler.platform.system')
    @patch('app.core.cpu_profiler.platform.machine')
    def test_fallback_profile(self, mock_machine, mock_system, mock_cpu_count):
        """Test fallback profile creation."""
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"
        mock_cpu_count.return_value = 8

        profile = self.profiler._get_fallback_profile()

        self.assertEqual(profile.architecture, "x86_64")
        self.assertEqual(profile.vendor, "Unknown")
        self.assertEqual(profile.cores_physical, 8)
        self.assertEqual(profile.cores_logical, 8)
        self.assertIsNone(profile.generation)
        self.assertEqual(profile.features, [])
        self.assertEqual(profile.name, "Unknown CPU")
        self.assertEqual(profile.platform_name, "Linux")


class TestThreadConfigManager(unittest.TestCase):
    """Test ThreadConfigManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manager = ThreadConfigManager(cache_dir=self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_optimal_config_apple_silicon(self):
        """Test optimal configuration generation for Apple Silicon."""
        profile = CPUProfile(
            architecture="arm64",
            vendor="Apple",
            cores_physical=8,
            cores_logical=8,
            generation=2,
            features=[],
            name="Apple M2",
            platform_name="Darwin"
        )

        config = self.manager._generate_optimal_config(profile)

        self.assertEqual(config.omp_threads, 8)
        self.assertEqual(config.openblas_threads, 1)  # Disabled to avoid conflicts
        self.assertEqual(config.veclib_threads, 8)

    def test_generate_optimal_config_intel_new(self):
        """Test optimal configuration generation for new Intel CPUs."""
        profile = CPUProfile(
            architecture="x86_64",
            vendor="Intel",
            cores_physical=8,
            cores_logical=16,
            generation=10,
            features=["AVX2"],
            name="Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz",
            platform_name="Windows"
        )

        config = self.manager._generate_optimal_config(profile)

        self.assertEqual(config.omp_threads, 6)  # min(6, 16)
        self.assertEqual(config.openblas_threads, 6)
        self.assertEqual(config.mkl_threads, 8)  # Physical cores
        self.assertEqual(config.intel_threads, 8)

    def test_generate_optimal_config_intel_old(self):
        """Test optimal configuration generation for older Intel CPUs."""
        profile = CPUProfile(
            architecture="x86_64",
            vendor="Intel",
            cores_physical=4,
            cores_logical=8,
            generation=8,
            features=["SSE4.2"],
            name="Intel(R) Core(TM) i5-8400 CPU @ 2.80GHz",
            platform_name="Windows"
        )

        config = self.manager._generate_optimal_config(profile)

        self.assertEqual(config.omp_threads, 3)  # Conservative for older CPUs
        self.assertEqual(config.openblas_threads, 3)
        self.assertEqual(config.mkl_threads, 4)  # Physical cores

    def test_generate_optimal_config_amd_ryzen(self):
        """Test optimal configuration generation for AMD Ryzen."""
        profile = CPUProfile(
            architecture="x86_64",
            vendor="AMD",
            cores_physical=6,
            cores_logical=12,
            generation=2,
            features=["AVX2"],
            name="AMD Ryzen 5 3600 6-Core Processor",
            platform_name="Linux"
        )

        config = self.manager._generate_optimal_config(profile)

        self.assertEqual(config.omp_threads, 6)  # Physical cores
        self.assertEqual(config.openblas_threads, 6)
        self.assertEqual(config.openblas_coretype, "RYZEN")

    def test_generate_optimal_config_unknown(self):
        """Test optimal configuration generation for unknown CPUs."""
        profile = CPUProfile(
            architecture="x86_64",
            vendor="Unknown",
            cores_physical=4,
            cores_logical=8,
            generation=None,
            features=[],
            name="Unknown CPU",
            platform_name="Linux"
        )

        config = self.manager._generate_optimal_config(profile)

        # Conservative fallback
        self.assertEqual(config.omp_threads, 2)  # min(3, max(2, 8 // 4))
        self.assertEqual(config.openblas_threads, 2)

    def test_caching_functionality(self):
        """Test configuration caching and loading."""
        profile = CPUProfile(
            architecture="x86_64",
            vendor="Intel",
            cores_physical=8,
            cores_logical=16,
            generation=10,
            features=["AVX2"],
            name="Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz",
            platform_name="Windows"
        )

        # Generate and cache configuration
        config1 = self.manager.get_optimal_config(profile)

        # Load from cache
        config2 = self.manager.get_optimal_config(profile)

        # Should be identical
        self.assertEqual(config1.omp_threads, config2.omp_threads)
        self.assertEqual(config1.openblas_threads, config2.openblas_threads)
        self.assertEqual(config1.mkl_threads, config2.mkl_threads)

        # Verify cache file exists
        self.assertTrue(self.manager.cache_file.exists())

        # Verify cache contents
        with open(self.manager.cache_file, 'r') as f:
            cache_data = json.load(f)

        signature = profile.signature()
        self.assertIn(signature, cache_data)

    def test_cache_corruption_handling(self):
        """Test handling of corrupted cache file."""
        # Create corrupted cache file
        with open(self.manager.cache_file, 'w') as f:
            f.write("invalid json content")

        profile = CPUProfile(
            architecture="x86_64",
            vendor="Intel",
            cores_physical=8,
            cores_logical=16,
            generation=10,
            features=["AVX2"],
            name="Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz",
            platform_name="Windows"
        )

        # Should handle corruption gracefully and generate new config
        config = self.manager.get_optimal_config(profile)
        self.assertIsNotNone(config)
        self.assertEqual(config.omp_threads, 6)


class TestAdaptiveThreadConfig(unittest.TestCase):
    """Test the main adaptive thread configuration function."""

    @patch('app.core.cpu_profiler.CPUProfiler')
    @patch('app.core.cpu_profiler.ThreadConfigManager')
    def test_get_adaptive_thread_config(self, mock_manager_class, mock_profiler_class):
        """Test the main get_adaptive_thread_config function."""
        # Mock CPU profile
        mock_profile = CPUProfile(
            architecture="x86_64",
            vendor="Intel",
            cores_physical=8,
            cores_logical=16,
            generation=10,
            features=["AVX2"],
            name="Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz",
            platform_name="Windows"
        )

        # Mock thread config
        mock_config = ThreadConfig(
            omp_threads=6,
            openblas_threads=6,
            mkl_threads=8,
            intel_threads=8
        )

        # Set up mocks
        mock_profiler = Mock()
        mock_profiler.detect_cpu_profile.return_value = mock_profile
        mock_profiler_class.return_value = mock_profiler

        mock_manager = Mock()
        mock_manager.get_optimal_config.return_value = mock_config
        mock_manager_class.return_value = mock_manager

        # Test the function
        result = get_adaptive_thread_config()

        # Verify calls were made
        mock_profiler_class.assert_called_once()
        mock_profiler.detect_cpu_profile.assert_called_once()
        mock_manager_class.assert_called_once()
        mock_manager.get_optimal_config.assert_called_once_with(mock_profile)

        # Verify result
        self.assertEqual(result, mock_config)


if __name__ == '__main__':
    unittest.main()