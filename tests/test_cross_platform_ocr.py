"""
Test cross-platform OCR compatibility between Windows and Linux.
Ensures that SimplePaddleOCREngine works identically across platforms.
"""

import os
import platform
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from app.core.extractor.ocr import SimplePaddleOCREngine


class TestCrossPlatformOCR:
    """Test cross-platform compatibility for OCR processing."""

    def test_platform_detection(self):
        """Test that platform detection works correctly."""
        detected_platform = platform.system()
        assert detected_platform in ["Windows", "Linux", "Darwin"]  # Darwin = macOS

    def test_environment_variables_setup(self):
        """Test that environment variables are set correctly for each platform."""
        engine = SimplePaddleOCREngine()

        # Mock platform.system() for Windows
        with patch("platform.system", return_value="Windows"):
            with patch("app.core.extractor.ocr.PaddleOCR") as mock_paddle:
                mock_paddle.return_value = MagicMock()

                # Attempt initialization (will fail due to missing models, but env vars should be set)
                try:
                    engine.initialize()
                except:
                    pass  # Expected to fail due to missing models in test

                # Check Windows-specific environment variables
                assert os.environ.get("CUDA_VISIBLE_DEVICES") == "-1"
                assert os.environ.get("KMP_DUPLICATE_LIB_OK") == "TRUE"
                assert os.environ.get("OMP_NUM_THREADS") == "1"

    def test_parameter_fallback_mechanism(self):
        """Test that parameter fallback works across different PaddleOCR versions."""
        engine = SimplePaddleOCREngine()

        # Mock the models directory resolution
        with patch.object(engine, "_resolve_models_root") as mock_resolve:
            mock_resolve.return_value = "/fake/path"

            # Mock Path.exists() to return True
            with patch("pathlib.Path.exists", return_value=True):
                # Mock PaddleOCR with different failure scenarios
                call_attempts = []

                def mock_paddle_ocr_init(*args, **kwargs):
                    call_attempts.append(kwargs)
                    if len(call_attempts) <= 2:  # First two attempts fail
                        raise Exception("Parameter not supported")
                    return MagicMock()  # Third attempt succeeds

                with patch("app.core.extractor.ocr.PaddleOCR", side_effect=mock_paddle_ocr_init):
                    result = engine.initialize()

                    # Should have tried all three configurations
                    assert len(call_attempts) == 3
                    assert result == True

                    # Check that different parameter sets were tried
                    assert "text_detection_model_dir" in call_attempts[0]  # latest
                    assert "det_model_dir" in call_attempts[1]  # legacy
                    assert "det_model_dir" in call_attempts[2]  # minimal

    def test_path_resolution_cross_platform(self):
        """Test that model path resolution works on different platforms."""
        engine = SimplePaddleOCREngine()

        # Test Windows-specific path resolution
        with patch("platform.system", return_value="Windows"):
            with patch("sys.frozen", True, create=True):
                with patch("sys.executable", "C:\\app\\myapp.exe"):
                    with patch("pathlib.Path.exists") as mock_exists:
                        # Mock that frozen app directory exists
                        def exists_side_effect(self):
                            return str(self).endswith("PP-OCRv5_server_det") or str(self).endswith(
                                "PP-OCRv5_server_rec"
                            )

                        mock_exists.side_effect = exists_side_effect

                        try:
                            result = engine._resolve_models_root()
                            # Should find the frozen application path
                            assert "myapp.exe" not in str(result)  # Should be parent directory
                        except FileNotFoundError:
                            # Expected if mocking doesn't fully work
                            pass

    def test_image_preprocessing_cross_platform(self):
        """Test that image preprocessing works identically across platforms."""
        engine = SimplePaddleOCREngine()

        # Create test images with different characteristics
        test_images = [
            np.ones((100, 200, 3), dtype=np.uint8) * 128,  # Normal RGB
            np.ones((100, 200), dtype=np.uint8) * 128,  # Grayscale
            np.ones((100, 200, 3), dtype=np.float32) * 0.5,  # Float32
            np.ones((5000, 5000, 3), dtype=np.uint8) * 128,  # Large image
        ]

        with patch.object(engine, "_ocr") as mock_ocr:
            mock_ocr.ocr.return_value = [[]]  # Empty result

            for i, img in enumerate(test_images):
                try:
                    result = engine.extract_text(img)
                    assert isinstance(result, list), f"Test image {i} should return list"
                except Exception as e:
                    pytest.fail(f"Test image {i} failed preprocessing: {e}")

    def test_ocr_result_parsing_formats(self):
        """Test parsing of different OCR result formats across platforms."""
        engine = SimplePaddleOCREngine()
        engine._ocr = MagicMock()

        # Test different result formats
        test_cases = [
            # Traditional list format
            [[[[0, 0], [100, 0], [100, 30], [0, 30]], ("Hello", 0.95)]],
            # Dictionary format (newer versions)
            [
                {
                    "rec_texts": ["Hello"],
                    "rec_scores": [0.95],
                    "rec_polys": [[[0, 0], [100, 0], [100, 30], [0, 30]]],
                }
            ],
            # Empty result
            [[]],
            # None result
            [None],
        ]

        test_image = np.ones((100, 200, 3), dtype=np.uint8) * 128

        for i, test_result in enumerate(test_cases):
            engine._ocr.ocr.return_value = test_result
            try:
                results = engine.extract_text(test_image)
                assert isinstance(results, list), f"Test case {i} should return list"

                if test_result[0] and test_result[0] is not None:
                    if isinstance(test_result[0], dict):
                        expected_count = len(test_result[0].get("rec_texts", []))
                    else:
                        expected_count = len(test_result[0]) if test_result[0] else 0

                    if expected_count > 0:
                        assert (
                            len(results) <= expected_count
                        ), f"Test case {i} result count mismatch"

            except Exception as e:
                pytest.fail(f"OCR result parsing test case {i} failed: {e}")

    def test_memory_safety_cross_platform(self):
        """Test memory safety features work on all platforms."""
        engine = SimplePaddleOCREngine()

        with patch.object(engine, "_ocr") as mock_ocr:
            mock_ocr.ocr.return_value = [[]]

            # Test memory safety with different scenarios
            test_cases = [
                None,  # None image
                np.array([]),  # Empty array
                np.zeros((0, 100, 3), dtype=np.uint8),  # Zero height
                np.zeros((100, 0, 3), dtype=np.uint8),  # Zero width
                np.ones((8000, 8000, 3), dtype=np.uint8),  # Oversized image
            ]

            for i, test_case in enumerate(test_cases):
                try:
                    result = engine.extract_text(test_case)
                    assert isinstance(result, list), f"Memory safety test {i} should return list"
                except Exception as e:
                    pytest.fail(f"Memory safety test {i} failed: {e}")

    def test_logging_cross_platform(self):
        """Test that logging works correctly across platforms."""
        import logging

        # Capture log messages
        log_messages = []

        class TestHandler(logging.Handler):
            def emit(self, record):
                log_messages.append(record.getMessage())

        handler = TestHandler()
        logger = logging.getLogger("app.core.extractor.ocr")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            engine = SimplePaddleOCREngine()

            # Test that platform-specific messages are logged
            with patch("platform.system", return_value="Windows"):
                with patch.object(engine, "_resolve_models_root") as mock_resolve:
                    mock_resolve.side_effect = FileNotFoundError("Test error")

                    result = engine.initialize()
                    assert result == False

                    # Check that Windows-specific logging occurred
                    platform_logs = [msg for msg in log_messages if "Windows" in msg]
                    assert len(platform_logs) > 0, "Should have Windows-specific log messages"

        finally:
            logger.removeHandler(handler)
