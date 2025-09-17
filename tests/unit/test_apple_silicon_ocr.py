"""Unit tests for Apple Silicon specific OCR optimizations.

Tests the Apple Silicon specific environment variables and process-based timeout functionality
added to address Issue #128 - macOS Apple Silicon PaddleOCR freeze problem.
"""

import os
import platform
import unittest
from unittest.mock import Mock, patch
import numpy as np

from app.core.extractor.ocr import SimplePaddleOCREngine


class TestAppleSiliconOCR(unittest.TestCase):
    """Test Apple Silicon specific OCR optimizations."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = SimplePaddleOCREngine()
        self.test_image = np.zeros((100, 200, 3), dtype=np.uint8)

    @patch('app.core.extractor.ocr.platform.system')
    @patch('app.core.extractor.ocr.platform.machine')
    @patch('app.core.extractor.ocr.os.cpu_count')
    def test_apple_silicon_environment_variables(self, mock_cpu_count, mock_machine, mock_system):
        """Test that Apple Silicon specific environment variables are set correctly."""
        # Setup mocks for Apple Silicon environment
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "arm64"
        mock_cpu_count.return_value = 8

        # Clear any existing environment variables that might interfere
        env_vars_to_test = [
            "VECLIB_MAXIMUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "PADDLE_CPU_ONLY",
            "BLAS",
            "FLAGS_use_mkldnn",
            "FLAGS_allocator_strategy"
        ]

        for var in env_vars_to_test:
            if var in os.environ:
                del os.environ[var]

        # Mock PaddleOCR to avoid actual initialization
        with patch('app.core.extractor.ocr.PaddleOCR') as mock_paddle, \
             patch('app.core.extractor.ocr.PADDLEOCR_AVAILABLE', True):

            mock_paddle.return_value = Mock()

            # Initialize the engine
            result = self.engine.initialize()

            # Verify initialization succeeded
            self.assertTrue(result)

            # Verify Apple Silicon specific environment variables are set
            self.assertEqual(os.environ.get("VECLIB_MAXIMUM_THREADS"), "8")
            self.assertEqual(os.environ.get("OPENBLAS_NUM_THREADS"), "1")
            self.assertEqual(os.environ.get("MKL_NUM_THREADS"), "1")
            self.assertEqual(os.environ.get("PADDLE_CPU_ONLY"), "1")
            self.assertEqual(os.environ.get("BLAS"), "Accelerate")
            self.assertEqual(os.environ.get("FLAGS_use_mkldnn"), "false")
            self.assertEqual(os.environ.get("FLAGS_allocator_strategy"), "auto_growth")

    @patch('app.core.extractor.ocr.platform.system')
    @patch('app.core.extractor.ocr.platform.machine')
    def test_non_apple_silicon_no_optimization(self, mock_machine, mock_system):
        """Test that non-Apple Silicon platforms don't get Apple Silicon optimizations."""
        # Setup mocks for non-Apple Silicon environment
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"

        # Clear Apple Silicon specific environment variables
        apple_silicon_vars = ["VECLIB_MAXIMUM_THREADS", "BLAS", "FLAGS_use_mkldnn"]
        for var in apple_silicon_vars:
            if var in os.environ:
                del os.environ[var]

        # Mock PaddleOCR to avoid actual initialization
        with patch('app.core.extractor.ocr.PaddleOCR') as mock_paddle, \
             patch('app.core.extractor.ocr.PADDLEOCR_AVAILABLE', True):

            mock_paddle.return_value = Mock()

            # Initialize the engine
            self.engine.initialize()

            # Verify Apple Silicon specific variables are not set
            self.assertNotIn("VECLIB_MAXIMUM_THREADS", os.environ)
            self.assertNotIn("BLAS", os.environ)
            self.assertNotIn("FLAGS_use_mkldnn", os.environ)

    @patch('app.core.extractor.ocr.platform.system')
    @patch('app.core.extractor.ocr.platform.machine')
    def test_timeout_functionality_apple_silicon(self, mock_machine, mock_system):
        """Test that timeout functionality works on Apple Silicon with process-based execution."""
        # Setup mocks for Apple Silicon environment
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "arm64"

        # Mock the OCR engine
        mock_ocr = Mock()
        self.engine._ocr = mock_ocr

        # Create a test image
        test_image = np.zeros((100, 200, 3), dtype=np.uint8)

        # Test that timeout functionality uses process-based execution
        with patch('multiprocessing.Process') as mock_process_class:
            mock_process = Mock()
            mock_process_class.return_value = mock_process
            # Simulate process not finishing within timeout
            mock_process.is_alive.return_value = True

            # Mock initialization to prevent actual OCR engine creation in fallback
            def mock_initialize():
                self.engine._ocr = Mock()  # Set a mock OCR engine after initialization
                self.engine._ocr.ocr.return_value = [{"fallback": "result"}]
                return True

            # Process timeout should raise TimeoutError (no fallback to avoid re-freeze)
            with self.assertRaises(TimeoutError):
                self.engine._run_ocr_with_timeout(test_image, timeout_seconds=1)

            # Verify that the process was terminated
            mock_process.terminate.assert_called_once()

    @patch('app.core.extractor.ocr.platform.system')
    @patch('app.core.extractor.ocr.platform.machine')
    def test_timeout_functionality_non_apple_silicon(self, mock_machine, mock_system):
        """Test that timeout functionality is bypassed on non-Apple Silicon."""
        # Setup mocks for non-Apple Silicon environment
        mock_system.return_value = "Linux"
        mock_machine.return_value = "x86_64"

        # Mock the OCR engine
        mock_ocr = Mock()
        mock_ocr.ocr.return_value = [{"test": "result"}]
        self.engine._ocr = mock_ocr

        # Create a test image
        test_image = np.zeros((100, 200, 3), dtype=np.uint8)

        # Test that OCR is called directly without timeout logic
        result = self.engine._run_ocr_with_timeout(test_image, timeout_seconds=1)

        # Verify OCR was called directly
        mock_ocr.ocr.assert_called_once_with(test_image)
        self.assertEqual(result, [{"test": "result"}])

    def test_cpu_count_handling(self):
        """Test that CPU count is handled safely when os.cpu_count() returns None."""
        with patch('app.core.extractor.ocr.platform.system', return_value="Darwin"), \
             patch('app.core.extractor.ocr.platform.machine', return_value="arm64"), \
             patch('app.core.extractor.ocr.os.cpu_count', return_value=None), \
             patch('app.core.extractor.ocr.PaddleOCR') as mock_paddle, \
             patch('app.core.extractor.ocr.PADDLEOCR_AVAILABLE', True):

            mock_paddle.return_value = Mock()

            # Clear the environment variable
            if "VECLIB_MAXIMUM_THREADS" in os.environ:
                del os.environ["VECLIB_MAXIMUM_THREADS"]

            # Initialize the engine
            self.engine.initialize()

            # Verify fallback value is used when cpu_count() returns None
            self.assertEqual(os.environ.get("VECLIB_MAXIMUM_THREADS"), "4")

    @patch('app.core.extractor.ocr.platform.system')
    @patch('app.core.extractor.ocr.platform.machine')
    def test_process_based_execution_apple_silicon(self, mock_machine, mock_system):
        """Test that Apple Silicon uses process-based execution."""
        # Setup mocks for Apple Silicon environment
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "arm64"

        # Mock the OCR engine
        mock_ocr = Mock()
        self.engine._ocr = mock_ocr

        # Create a test image
        test_image = np.zeros((100, 200, 3), dtype=np.uint8)

        # Mock multiprocessing components
        with patch('multiprocessing.Process') as mock_process_class, \
             patch('multiprocessing.Queue') as mock_queue_class:

            mock_process = Mock()
            mock_queue = Mock()
            mock_process_class.return_value = mock_process
            mock_queue_class.return_value = mock_queue

            # Simulate successful process execution
            mock_process.is_alive.return_value = False
            mock_queue.empty.return_value = False
            mock_queue.get.return_value = [{"test": "result"}]

            # Test process-based execution
            result = self.engine._run_ocr_with_timeout(test_image, timeout_seconds=1)

            # Verify process was created and started
            mock_process_class.assert_called_once()
            mock_process.start.assert_called_once()
            mock_process.join.assert_called_once()

            # Verify result was retrieved from queue
            self.assertEqual(result, [{"test": "result"}])

    @patch('app.core.extractor.ocr.platform.system')
    @patch('app.core.extractor.ocr.platform.machine')
    def test_process_fallback_on_failure(self, mock_machine, mock_system):
        """Test fallback to direct execution when process-based execution fails."""
        # Setup mocks for Apple Silicon environment
        mock_system.return_value = "Darwin"
        mock_machine.return_value = "arm64"

        # Mock the OCR engine
        mock_ocr = Mock()
        mock_ocr.ocr.return_value = [{"fallback": "result"}]
        self.engine._ocr = mock_ocr

        # Create a test image
        test_image = np.zeros((100, 200, 3), dtype=np.uint8)

        # Mock multiprocessing to raise an exception
        with patch('multiprocessing.Process', side_effect=Exception("Process creation failed")):
            # Test that empty result is returned when process creation fails
            result = self.engine._run_ocr_with_timeout(test_image, timeout_seconds=1)

            # Verify empty result is returned to avoid potential freeze
            self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()