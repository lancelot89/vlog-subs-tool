"""Integration test for adaptive thread configuration system.

Tests the integration between CPU profiler and OCR system without requiring
heavy dependencies like OpenCV or PaddleOCR.
"""

import os
import platform
import unittest
from unittest.mock import Mock, patch

from app.core.cpu_profiler import (
    CPUProfile,
    ThreadConfig,
    get_adaptive_thread_config
)


class TestAdaptiveThreadIntegration(unittest.TestCase):
    """Test adaptive thread configuration integration."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear environment variables that might interfere
        env_vars = [
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "INTEL_NUM_THREADS",
            "OPENBLAS_CORETYPE"
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

    def test_adaptive_config_intel_windows(self):
        """Test adaptive configuration for Intel CPU on Windows."""
        with patch('app.core.cpu_profiler.CPUProfiler') as mock_profiler_class:
            # Mock Intel 10th gen CPU profile
            mock_profile = CPUProfile(
                architecture="x86_64",
                vendor="Intel",
                cores_physical=8,
                cores_logical=16,
                generation=10,
                features=["AVX2", "SSE4.2"],
                name="Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz",
                platform_name="Windows"
            )

            mock_profiler = Mock()
            mock_profiler.detect_cpu_profile.return_value = mock_profile
            mock_profiler_class.return_value = mock_profiler

            # Get adaptive configuration
            config = get_adaptive_thread_config()

            # Verify Intel optimization
            self.assertEqual(config.omp_threads, 6)  # min(6, 16)
            self.assertEqual(config.openblas_threads, 6)
            self.assertEqual(config.mkl_threads, 8)  # Physical cores
            self.assertEqual(config.intel_threads, 8)

            # Verify environment variables would be set correctly
            env_vars = config.to_env_vars()
            self.assertEqual(env_vars["OMP_NUM_THREADS"], "6")
            self.assertEqual(env_vars["OPENBLAS_NUM_THREADS"], "6")
            self.assertEqual(env_vars["MKL_NUM_THREADS"], "8")
            self.assertEqual(env_vars["INTEL_NUM_THREADS"], "8")

    def test_adaptive_config_amd_linux(self):
        """Test adaptive configuration for AMD Ryzen on Linux."""
        with patch('app.core.cpu_profiler.CPUProfiler') as mock_profiler_class:
            # Mock AMD Ryzen CPU profile
            mock_profile = CPUProfile(
                architecture="x86_64",
                vendor="AMD",
                cores_physical=6,
                cores_logical=12,
                generation=2,  # Zen 2
                features=["AVX2", "SSE4.2"],
                name="AMD Ryzen 5 3600 6-Core Processor",
                platform_name="Linux"
            )

            mock_profiler = Mock()
            mock_profiler.detect_cpu_profile.return_value = mock_profile
            mock_profiler_class.return_value = mock_profiler

            # Get adaptive configuration
            config = get_adaptive_thread_config()

            # Verify AMD optimization
            self.assertEqual(config.omp_threads, 6)  # Physical cores
            self.assertEqual(config.openblas_threads, 6)
            self.assertEqual(config.openblas_coretype, "RYZEN")

            # Verify environment variables
            env_vars = config.to_env_vars()
            self.assertEqual(env_vars["OMP_NUM_THREADS"], "6")
            self.assertEqual(env_vars["OPENBLAS_NUM_THREADS"], "6")
            self.assertEqual(env_vars["OPENBLAS_CORETYPE"], "RYZEN")

    def test_adaptive_config_apple_silicon(self):
        """Test adaptive configuration for Apple Silicon."""
        with patch('app.core.cpu_profiler.CPUProfiler') as mock_profiler_class:
            # Mock Apple Silicon CPU profile
            mock_profile = CPUProfile(
                architecture="arm64",
                vendor="Apple",
                cores_physical=8,
                cores_logical=8,
                generation=2,  # M2
                features=[],
                name="Apple M2",
                platform_name="Darwin"
            )

            mock_profiler = Mock()
            mock_profiler.detect_cpu_profile.return_value = mock_profile
            mock_profiler_class.return_value = mock_profiler

            # Get adaptive configuration
            config = get_adaptive_thread_config()

            # Verify Apple Silicon optimization
            self.assertEqual(config.omp_threads, 8)
            self.assertEqual(config.openblas_threads, 1)  # Disabled to avoid conflicts
            self.assertEqual(config.veclib_threads, 8)

            # Verify environment variables
            env_vars = config.to_env_vars()
            self.assertEqual(env_vars["OMP_NUM_THREADS"], "8")
            self.assertEqual(env_vars["OPENBLAS_NUM_THREADS"], "1")
            self.assertEqual(env_vars["VECLIB_MAXIMUM_THREADS"], "8")

    def test_adaptive_config_unknown_cpu(self):
        """Test adaptive configuration for unknown CPU (fallback)."""
        with patch('app.core.cpu_profiler.CPUProfiler') as mock_profiler_class:
            # Mock unknown CPU profile
            mock_profile = CPUProfile(
                architecture="x86_64",
                vendor="Unknown",
                cores_physical=4,
                cores_logical=8,
                generation=None,
                features=[],
                name="Unknown CPU",
                platform_name="Linux"
            )

            mock_profiler = Mock()
            mock_profiler.detect_cpu_profile.return_value = mock_profile
            mock_profiler_class.return_value = mock_profiler

            # Get adaptive configuration
            config = get_adaptive_thread_config()

            # Verify conservative fallback
            self.assertEqual(config.omp_threads, 2)  # min(3, max(2, 8 // 4))
            self.assertEqual(config.openblas_threads, 2)

            # Verify environment variables
            env_vars = config.to_env_vars()
            self.assertEqual(env_vars["OMP_NUM_THREADS"], "2")
            self.assertEqual(env_vars["OPENBLAS_NUM_THREADS"], "2")

    @patch('app.core.cpu_profiler.logger')
    def test_adaptive_config_error_handling(self, mock_logger):
        """Test error handling in adaptive configuration."""
        with patch('app.core.cpu_profiler.CPUProfiler') as mock_profiler_class:
            # Mock profiler that raises an exception during detection
            mock_profiler = Mock()
            mock_profiler.detect_cpu_profile.side_effect = Exception("CPU detection failed")
            mock_profiler_class.return_value = mock_profiler

            # Get adaptive configuration (should handle error gracefully)
            config = get_adaptive_thread_config()

            # Should return fallback configuration even on error
            self.assertIsNotNone(config)
            self.assertIsInstance(config, ThreadConfig)

            # Should log the error
            mock_logger.warning.assert_called()

    def test_cache_persistence(self):
        """Test that configurations are cached and reused."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('app.core.cpu_profiler.ThreadConfigManager') as mock_manager_class:
                # Mock cache directory
                cache_dir = Path(temp_dir)

                # Mock profile and config
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

                mock_config = ThreadConfig(
                    omp_threads=6,
                    openblas_threads=6,
                    mkl_threads=8,
                    intel_threads=8
                )

                # Set up mock manager
                mock_manager = Mock()
                mock_manager.get_optimal_config.return_value = mock_config
                mock_manager_class.return_value = mock_manager

                with patch('app.core.cpu_profiler.CPUProfiler') as mock_profiler_class:
                    mock_profiler = Mock()
                    mock_profiler.detect_cpu_profile.return_value = mock_profile
                    mock_profiler_class.return_value = mock_profiler

                    # First call
                    config1 = get_adaptive_thread_config()

                    # Second call
                    config2 = get_adaptive_thread_config()

                    # Both should return the same configuration
                    self.assertEqual(config1.omp_threads, config2.omp_threads)
                    self.assertEqual(config1.openblas_threads, config2.openblas_threads)

    def test_configuration_signature_uniqueness(self):
        """Test that different CPU profiles generate unique signatures."""
        profiles = [
            CPUProfile("x86_64", "Intel", 8, 16, 10, ["AVX2"], "Intel i7-10700K", "Windows"),
            CPUProfile("x86_64", "AMD", 6, 12, 2, ["AVX2"], "AMD Ryzen 5 3600", "Linux"),
            CPUProfile("arm64", "Apple", 8, 8, 2, [], "Apple M2", "Darwin"),
            CPUProfile("x86_64", "Intel", 4, 8, 8, ["SSE4.2"], "Intel i5-8400", "Windows"),
        ]

        signatures = [profile.signature() for profile in profiles]

        # All signatures should be unique
        self.assertEqual(len(signatures), len(set(signatures)))

        # Signatures should be deterministic
        for profile in profiles:
            sig1 = profile.signature()
            sig2 = profile.signature()
            self.assertEqual(sig1, sig2)


if __name__ == '__main__':
    unittest.main()