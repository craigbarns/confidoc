"""Tests for OCR image preprocessing pipeline."""

from unittest.mock import MagicMock, patch

import pytest

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

pytestmark = pytest.mark.skipif(not HAS_PIL, reason="Pillow not installed")

from app.services.anonymization_service import (
    _deskew_image,
    _get_tesseract_config,
    _preprocess_image_for_ocr,
)


class TestPreprocessImageForOCR:
    """Test image preprocessing pipeline."""

    def test_converts_to_grayscale(self):
        img = Image.new("RGB", (2000, 2000), color=(128, 64, 32))
        result = _preprocess_image_for_ocr(img)
        assert result.mode == "L"

    def test_upscales_small_images(self):
        img = Image.new("L", (400, 400), color=128)
        result = _preprocess_image_for_ocr(img)
        assert result.size[0] > 400
        assert result.size[1] > 400

    def test_does_not_upscale_large_images(self):
        img = Image.new("L", (3000, 3000), color=128)
        result = _preprocess_image_for_ocr(img)
        assert result.size[0] >= 2000

    def test_handles_rgba_input(self):
        img = Image.new("RGBA", (2000, 2000), color=(128, 64, 32, 200))
        result = _preprocess_image_for_ocr(img)
        assert result.mode == "L"

    def test_handles_1bit_input(self):
        img = Image.new("1", (2000, 2000))
        result = _preprocess_image_for_ocr(img)
        assert result.mode == "L"

    def test_output_is_pil_image(self):
        img = Image.new("RGB", (2000, 2000), color=(0, 0, 0))
        result = _preprocess_image_for_ocr(img)
        assert isinstance(result, Image.Image)


@pytest.mark.skipif(not HAS_NUMPY, reason="numpy not installed")
class TestDeskewImage:
    """Test deskew functionality."""

    def test_straight_image_stays_straight(self):
        img = Image.new("L", (500, 500), color=255)
        for x in range(100, 400):
            img.putpixel((x, 250), 0)
        result = _deskew_image(img)
        assert isinstance(result, Image.Image)

    def test_returns_image(self):
        img = Image.new("L", (200, 200), color=200)
        result = _deskew_image(img)
        assert isinstance(result, Image.Image)


class TestGetTesseractConfig:
    """Test Tesseract configuration string."""

    def test_contains_oem(self):
        config = _get_tesseract_config()
        assert "--oem 3" in config

    def test_contains_psm(self):
        config = _get_tesseract_config()
        assert "--psm 6" in config

    def test_preserves_interword_spaces(self):
        config = _get_tesseract_config()
        assert "preserve_interword_spaces=1" in config
