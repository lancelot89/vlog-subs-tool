"""Unit tests for Windows OCR performance optimizations.

Tests the Windows specific CPU detection, thread optimization, and progressive
feature enablement added to address Issue #129 - Windows OCR performance improvement.
"""

import os
import platform
import unittest
from unittest.mock import Mock, patch, call
import subprocess

from app.core.extractor.ocr import (
    SimplePaddleOCREngine,
    _get_cpu_info,
    _get_cpu_generation,
    _get_optimal_windows_threads
)


class TestWindowsOCRPerformance(unittest.TestCase):
    """Test Windows OCR performance optimizations."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = SimplePaddleOCREngine()

    @patch('app.core.extractor.ocr.subprocess.run')
    @patch('app.core.extractor.ocr.platform.system')
    def test_get_cpu_info_windows(self, mock_platform, mock_subprocess):
        """Test CPU information retrieval on Windows."""
        mock_platform.return_value = "Windows"

        # Mock wmic output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """Node,Name,NumberOfCores,NumberOfLogicalProcessors
DESKTOP,Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz,8,16
"""
        mock_subprocess.return_value = mock_result

        cpu_info = _get_cpu_info()

        self.assertEqual(cpu_info["name"], "Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz")
        self.assertEqual(cpu_info["cores"], 8)
        self.assertEqual(cpu_info["logical_processors"], 16)
        mock_subprocess.assert_called_once()

    @patch('builtins.open', side_effect=FileNotFoundError)
    @patch('app.core.extractor.ocr.platform.system')
    def test_get_cpu_info_linux(self, mock_platform, mock_open):
        """Test CPU information retrieval on Linux."""
        mock_platform.return_value = "Linux"

        # Mock /proc/cpuinfo content
        cpuinfo_content = """processor	: 0
model name	: Intel(R) Core(TM) i5-9400 CPU @ 2.90GHz
processor	: 1
model name	: Intel(R) Core(TM) i5-9400 CPU @ 2.90GHz
"""

        # Reset the mock to allow proper usage
        mock_open.side_effect = None
        with patch('builtins.open', unittest.mock.mock_open(read_data=cpuinfo_content)):
            cpu_info = _get_cpu_info()

        self.assertIn("Intel(R) Core(TM) i5-9400 CPU @ 2.90GHz", cpu_info["name"])
        self.assertEqual(cpu_info["cores"], 2)

    def test_get_cpu_generation_intel(self):
        """Test Intel CPU generation detection."""
        test_cases = [
            ("Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz", 10),
            ("Intel(R) Core(TM) i5-11400 CPU @ 2.60GHz", 11),
            ("12th Gen Intel(R) Core(TM) i9-12900K", 12),
            ("Intel(R) Core(TM) i3-8100 CPU @ 3.60GHz", 8),
            ("AMD Ryzen 5 3600", 8),  # Fallback for non-Intel
        ]

        for cpu_name, expected_gen in test_cases:
            with self.subTest(cpu_name=cpu_name):
                result = _get_cpu_generation(cpu_name)
                self.assertEqual(result, expected_gen)

    def test_get_optimal_windows_threads_intel_new(self):
        """Test optimal thread calculation for new Intel CPUs."""
        cpu_info = {
            "name": "Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz",
            "logical_processors": 16
        }

        optimal = _get_optimal_windows_threads(cpu_info)
        self.assertEqual(optimal, 6)  # min(6, max(2, 16))

    def test_get_optimal_windows_threads_intel_old(self):
        """Test optimal thread calculation for older Intel CPUs."""
        cpu_info = {
            "name": "Intel(R) Core(TM) i5-8400 CPU @ 2.80GHz",
            "logical_processors": 6
        }

        optimal = _get_optimal_windows_threads(cpu_info)
        self.assertEqual(optimal, 3)  # min(4, max(2, 6 // 2)) = min(4, max(2, 3)) = min(4, 3) = 3

    def test_get_optimal_windows_threads_amd_ryzen(self):
        """Test optimal thread calculation for AMD Ryzen CPUs."""
        cpu_info = {
            "name": "AMD Ryzen 5 3600 6-Core Processor",
            "logical_processors": 12
        }

        optimal = _get_optimal_windows_threads(cpu_info)
        self.assertEqual(optimal, 6)  # min(6, max(2, 12))

    def test_get_optimal_windows_threads_unknown_cpu(self):
        """Test optimal thread calculation for unknown CPUs."""
        cpu_info = {
            "name": "Unknown Processor",
            "logical_processors": 8
        }

        optimal = _get_optimal_windows_threads(cpu_info)
        self.assertEqual(optimal, 2)  # min(3, max(2, 8 // 4)) = min(3, max(2, 2)) = min(3, 2) = 2

    @patch('app.core.extractor.ocr.platform.system')
    @patch('app.core.extractor.ocr._get_cpu_info')
    def test_windows_environment_optimization(self, mock_cpu_info, mock_platform):
        """Test Windows environment variable optimization."""
        mock_platform.return_value = "Windows"
        mock_cpu_info.return_value = {
            "name": "Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz",
            "logical_processors": 16
        }

        # Clear relevant environment variables
        env_vars = ["OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

        with patch('app.core.extractor.ocr.PaddleOCR') as mock_paddle, \
             patch('app.core.extractor.ocr.PADDLEOCR_AVAILABLE', True):

            mock_paddle.return_value = Mock()
            result = self.engine.initialize()

        self.assertTrue(result)
        # Verify optimal thread settings
        self.assertEqual(os.environ.get("OMP_NUM_THREADS"), "6")
        self.assertEqual(os.environ.get("OPENBLAS_NUM_THREADS"), "6")
        self.assertEqual(os.environ.get("MKL_NUM_THREADS"), "6")  # Intel specific

    @patch('app.core.extractor.ocr.platform.system')
    @patch('app.core.extractor.ocr._get_cpu_info')
    def test_windows_amd_optimization(self, mock_cpu_info, mock_platform):
        """Test Windows AMD specific optimizations."""
        mock_platform.return_value = "Windows"
        mock_cpu_info.return_value = {
            "name": "AMD Ryzen 5 3600 6-Core Processor",
            "logical_processors": 12
        }

        # Clear environment variable
        if "OPENBLAS_CORETYPE" in os.environ:
            del os.environ["OPENBLAS_CORETYPE"]

        with patch('app.core.extractor.ocr.PaddleOCR') as mock_paddle, \
             patch('app.core.extractor.ocr.PADDLEOCR_AVAILABLE', True):

            mock_paddle.return_value = Mock()
            self.engine.initialize()

        # Verify AMD specific settings
        self.assertEqual(os.environ.get("OPENBLAS_CORETYPE"), "RYZEN")

    @patch('app.core.extractor.ocr.platform.system')
    @patch('app.core.extractor.ocr._get_cpu_info')
    def test_windows_progressive_configuration(self, mock_cpu_info, mock_platform):
        """Test Windows progressive configuration fallback."""
        mock_platform.return_value = "Windows"
        mock_cpu_info.return_value = {
            "name": "Intel(R) Core(TM) i7-10700K CPU @ 3.80GHz",
            "logical_processors": 16
        }

        with patch('app.core.extractor.ocr.PaddleOCR') as mock_paddle, \
             patch('app.core.extractor.ocr.PADDLEOCR_AVAILABLE', True):

            # First call fails, second succeeds
            mock_paddle.side_effect = [Exception("MKLDNN failed"), Mock()]

            result = self.engine.initialize()

        self.assertTrue(result)
        # Should have tried twice (aggressive config failed, moderate succeeded)
        self.assertEqual(mock_paddle.call_count, 2)

    @patch('app.core.extractor.ocr.platform.system')
    def test_non_windows_unchanged(self, mock_platform):
        """Test that non-Windows platforms are unchanged."""
        mock_platform.return_value = "Linux"

        with patch('app.core.extractor.ocr.PaddleOCR') as mock_paddle, \
             patch('app.core.extractor.ocr.PADDLEOCR_AVAILABLE', True):

            mock_paddle.return_value = Mock()
            self.engine.initialize()

        # Should use traditional configuration path
        mock_paddle.assert_called_once()
        # Verify traditional Linux-style configuration was used
        call_args = mock_paddle.call_args[1]
        self.assertIn("use_textline_orientation", call_args)
        self.assertTrue(call_args.get("use_textline_orientation", False))

    def test_cpu_info_fallback(self):
        """Test CPU info fallback when detection fails."""
        with patch('app.core.extractor.ocr.subprocess.run', side_effect=Exception("Command failed")), \
             patch('app.core.extractor.ocr.platform.system', return_value="Windows"):

            cpu_info = _get_cpu_info()

        # Should return fallback values
        self.assertEqual(cpu_info["name"], "Unknown")
        self.assertGreaterEqual(cpu_info["cores"], 4)
        self.assertGreaterEqual(cpu_info["logical_processors"], 4)


if __name__ == '__main__':
    unittest.main()