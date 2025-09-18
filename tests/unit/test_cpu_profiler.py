"""Unit tests for the simplified CPU profiler.

Tests basic CPU detection and thread configuration.
"""

import os
import platform
import unittest
from unittest.mock import patch

from app.core.cpu_profiler import (
    ThreadConfig,
    CPUProfiler,
    get_adaptive_thread_config,
    get_cpu_count
)


class TestThreadConfig(unittest.TestCase):
    """Test ThreadConfig functionality."""

    def test_thread_config_creation(self):
        """Test ThreadConfig creation."""
        config = ThreadConfig(omp_threads=2, openblas_threads=2)
        self.assertEqual(config.omp_threads, 2)
        self.assertEqual(config.openblas_threads, 2)

    def test_to_env_vars(self):
        """Test environment variable conversion."""
        config = ThreadConfig(omp_threads=4, openblas_threads=4)
        env_vars = config.to_env_vars()

        expected = {
            'OMP_NUM_THREADS': '4',
            'OPENBLAS_NUM_THREADS': '4',
            'MKL_NUM_THREADS': '4',
            'VECLIB_MAXIMUM_THREADS': '4',
        }

        self.assertEqual(env_vars, expected)


class TestCPUDetection(unittest.TestCase):
    """Test CPU detection functions."""

    def test_get_cpu_count(self):
        """Test CPU count detection."""
        count = get_cpu_count()
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 1)

    @patch('os.cpu_count')
    def test_get_cpu_count_fallback(self, mock_cpu_count):
        """Test CPU count fallback when os.cpu_count() returns None."""
        mock_cpu_count.return_value = None
        count = get_cpu_count()
        self.assertEqual(count, 1)

    def test_get_adaptive_thread_config(self):
        """Test adaptive thread configuration."""
        config = get_adaptive_thread_config()
        self.assertIsInstance(config, ThreadConfig)
        self.assertGreaterEqual(config.omp_threads, 1)
        self.assertLessEqual(config.omp_threads, 4)
        self.assertEqual(config.omp_threads, config.openblas_threads)


class TestCPUProfiler(unittest.TestCase):
    """Test CPUProfiler class."""

    def setUp(self):
        """Set up test profiler."""
        self.profiler = CPUProfiler()

    def test_profiler_initialization(self):
        """Test profiler initialization."""
        self.assertGreaterEqual(self.profiler.cpu_count, 1)
        self.assertIn(self.profiler.platform, ['Windows', 'Darwin', 'Linux'])

    def test_detect_cpu_profile(self):
        """Test CPU profile detection."""
        profile = self.profiler.detect_cpu_profile()

        self.assertIsInstance(profile, dict)
        self.assertIn('cores_physical', profile)
        self.assertIn('cores_logical', profile)
        self.assertIn('platform_name', profile)
        self.assertIn('vendor', profile)
        self.assertIn('architecture', profile)
        self.assertIn('name', profile)

    def test_get_optimal_thread_count(self):
        """Test optimal thread count calculation."""
        thread_count = self.profiler.get_optimal_thread_count()
        self.assertIsInstance(thread_count, int)
        self.assertGreaterEqual(thread_count, 1)
        self.assertLessEqual(thread_count, 4)


if __name__ == '__main__':
    unittest.main()