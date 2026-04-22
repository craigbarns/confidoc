"""ConfiDoc Backend — OCR Preprocessing Service."""

import contextlib
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

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


def preprocess_image_for_ocr(img: "Image.Image") -> "Image.Image":
    """Apply a multi-step preprocessing pipeline to boost OCR accuracy."""
    if not HAS_PIL:
        return img
        
    # 1. Grayscale
    img = img.convert("L")

    # 2. Up-scale small images — Tesseract works best at 300+ DPI
    width, height = img.size
    if width < 1800 or height < 1800:
        scale = max(2, 2400 // min(width, height))
        scale = min(scale, 4)  # cap at 4x
        img = img.resize((width * scale, height * scale), Image.LANCZOS)

    # 3. Denoise — removes speckles from scans
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # 4. Contrast enhancement
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.8)

    # 5. Sharpen — recover edges after denoise
    img = img.filter(ImageFilter.SHARPEN)

    # 6. Binarize (black & white) — adaptive autocontrast + threshold
    img = ImageOps.autocontrast(img, cutoff=2)

    # 7. Deskew (straighten tilted scans) — requires numpy
    if HAS_NUMPY:
        with contextlib.suppress(Exception):
            img = _deskew_image(img)

    return img


def _deskew_image(img: "Image.Image") -> "Image.Image":
    """Deskew a grayscale image by detecting dominant line angle."""
    if not HAS_NUMPY:
        return img
        
    # Compute horizontal projection profile variance at different angles
    best_angle = 0.0
    best_score = 0.0
    for angle_10x in range(-50, 51, 5):  # -5.0° to +5.0° in 0.5° steps
        angle = angle_10x / 10.0
        rotated = img.rotate(angle, fillcolor=255, expand=False)
        row_sums = np.sum(np.array(rotated) < 128, axis=1)
        score = float(np.var(row_sums))
        if score > best_score:
            best_score = score
            best_angle = angle
    if abs(best_angle) > 0.3:
        img = img.rotate(best_angle, fillcolor=255, expand=True)
        logger.debug("deskew_applied", angle=best_angle)
    return img
