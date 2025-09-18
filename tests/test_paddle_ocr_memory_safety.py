"""
Test PaddleOCR memory safety and large image handling.
Tests the fixes for malloc() and std::bad_array_new_length errors.
"""

import cv2
import numpy as np
import pytest

from app.core.extractor.ocr import SimplePaddleOCREngine


class TestPaddleOCRMemorySafety:
    """Test memory safety improvements for PaddleOCR."""

    @pytest.fixture
    def ocr_engine(self):
        """Create and initialize OCR engine."""
        engine = SimplePaddleOCREngine()
        if not engine.initialize():
            pytest.skip("PaddleOCR initialization failed")
        return engine

    def test_empty_image_handling(self, ocr_engine):
        """Test handling of empty/null images."""
        # Test None image
        results = ocr_engine.extract_text(None)
        assert results == []

        # Test empty array
        empty_img = np.array([])
        results = ocr_engine.extract_text(empty_img)
        assert results == []

    def test_invalid_dimension_images(self, ocr_engine):
        """Test handling of images with invalid dimensions."""
        # Zero dimensions
        zero_img = np.zeros((0, 100, 3), dtype=np.uint8)
        results = ocr_engine.extract_text(zero_img)
        assert results == []

        # Negative dimensions (not possible in numpy but test edge case)
        invalid_img = np.zeros((1, 1, 3), dtype=np.uint8)
        results = ocr_engine.extract_text(invalid_img)
        assert isinstance(results, list)

    def test_large_image_resizing(self, ocr_engine):
        """Test automatic resizing of oversized images."""
        # Create 8K image (should be resized)
        large_img = np.ones((7680, 4320, 3), dtype=np.uint8) * 128

        # Add some text-like pattern
        cv2.rectangle(large_img, (1000, 3000), (3000, 3500), (255, 255, 255), -1)
        cv2.rectangle(large_img, (1100, 3100), (2900, 3400), (0, 0, 0), 50)

        results = ocr_engine.extract_text(large_img)
        assert isinstance(results, list)  # Should not crash

    def test_memory_contiguous_array(self, ocr_engine):
        """Test handling of non-contiguous memory arrays."""
        # Create non-contiguous array
        img = np.ones((1000, 1000, 3), dtype=np.uint8) * 128
        non_contiguous = img[::2, ::2]  # Non-contiguous slice

        results = ocr_engine.extract_text(non_contiguous)
        assert isinstance(results, list)  # Should not crash

    def test_different_data_types(self, ocr_engine):
        """Test handling of different numpy data types."""
        base_img = np.ones((500, 500, 3)) * 128

        # Test float64
        float_img = base_img.astype(np.float64)
        results = ocr_engine.extract_text(float_img)
        assert isinstance(results, list)

        # Test int32
        int_img = base_img.astype(np.int32)
        results = ocr_engine.extract_text(int_img)
        assert isinstance(results, list)

    def test_grayscale_conversion(self, ocr_engine):
        """Test grayscale to BGR conversion."""
        gray_img = np.ones((500, 500), dtype=np.uint8) * 128
        results = ocr_engine.extract_text(gray_img)
        assert isinstance(results, list)  # Should not crash

    def test_memory_limit_parameters(self):
        """Test OCR engine initialization with memory safety parameters."""
        engine = SimplePaddleOCREngine(max_batch_size=1)
        assert engine.max_batch_size == 1

        # Test initialization succeeds with safety parameters
        success = engine.initialize()
        if success:
            assert engine._ocr is not None

    def test_realistic_vlog_frame_size(self, ocr_engine):
        """Test with realistic video frame sizes (1080p, 4K)."""
        # 1080p frame
        hd_frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 64
        cv2.rectangle(hd_frame, (100, 900), (1800, 1000), (255, 255, 255), -1)

        results = ocr_engine.extract_text(hd_frame)
        assert isinstance(results, list)

        # 4K frame (should be at the limit)
        uhd_frame = np.ones((2160, 3840, 3), dtype=np.uint8) * 64
        cv2.rectangle(uhd_frame, (200, 1800), (3600, 2000), (255, 255, 255), -1)

        results = ocr_engine.extract_text(uhd_frame)
        assert isinstance(results, list)

    def test_error_recovery(self, ocr_engine):
        """Test that the engine can recover from errors."""
        # First, process a problematic image
        problematic_img = np.zeros((1, 1, 3), dtype=np.uint8)
        results1 = ocr_engine.extract_text(problematic_img)

        # Then, process a normal image
        normal_img = np.ones((100, 200, 3), dtype=np.uint8) * 128
        results2 = ocr_engine.extract_text(normal_img)

        # Both should return lists without crashing
        assert isinstance(results1, list)
        assert isinstance(results2, list)
