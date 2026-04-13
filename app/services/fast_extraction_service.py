"""ConfiDoc — Fast extraction service (PyMuPDF + Tesseract fallback).

Replaces slow Docling for the Celery worker. Native PDF text extraction
is instant; OCR via pytesseract/pdf2image is used only for scanned docs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def _extract_with_pymupdf(file_content: bytes) -> tuple[str, int]:
    """Extract native text from PDF using PyMuPDF (fitz)."""
    import fitz  # PyMuPDF

    text_parts: list[str] = []
    with fitz.open(stream=file_content, filetype="pdf") as doc:
        page_count = len(doc)
        for page in doc:
            text_parts.append(page.get_text())
    return "\n\n".join(text_parts), page_count


def _extract_with_ocr(file_content: bytes) -> tuple[str, int]:
    """OCR fallback for scanned PDFs using pdf2image + pytesseract."""
    from pdf2image import convert_from_path
    import pytesseract

    suffix = ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name

    try:
        images = convert_from_path(tmp_path, dpi=200)
        texts: list[str] = []
        for img in images:
            page_text = pytesseract.image_to_string(img, lang="fra+eng")
            texts.append(page_text)
        return "\n\n".join(texts), len(images)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def extract_text_sync(file_content: bytes, extension: str = "pdf") -> dict[str, Any]:
    """Fast synchronous text extraction.

    Returns:
        {"text": "...", "pages": N, "method": "pymupdf|ocr", "error": None}
    """
    empty = {"text": "", "pages": 0, "method": "unknown", "error": None}

    if extension.lower() != "pdf":
        # For images, use OCR directly
        try:
            import pytesseract
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(file_content))
            text = pytesseract.image_to_string(img, lang="fra+eng")
            return {
                "text": text,
                "pages": 1,
                "method": "ocr",
                "error": None,
            }
        except Exception as exc:
            logger.error("image_ocr_failed", error=str(exc))
            empty["error"] = str(exc)
            return empty

    # PDF: try PyMuPDF first
    try:
        text, page_count = _extract_with_pymupdf(file_content)
        # If very little native text, assume scanned PDF and OCR
        if len(text.strip()) < 100:
            logger.info("pymupdf_text_too_short_ocr_fallback", chars=len(text))
            text, page_count = _extract_with_ocr(file_content)
            method = "ocr"
        else:
            method = "pymupdf"

        logger.info("fast_extraction_complete", method=method, pages=page_count, chars=len(text))
        return {"text": text, "pages": page_count, "method": method, "error": None}
    except Exception as exc:
        logger.error("fast_extraction_failed", error=str(exc))
        empty["error"] = str(exc)
        return empty
