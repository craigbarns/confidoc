"""ConfiDoc Backend — Extraction Service."""

import os
import tempfile
from io import BytesIO
from typing import Any

import fitz

from app.core.logging import get_logger
from app.core.text_sanitize import postgres_safe_text
from app.services.ocr.engines import extract_pdf_text_via_ocr_engines, ocr_image

logger = get_logger(__name__)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pymupdf4llm
    HAS_MD_EXTRACTOR = True
except ImportError:
    HAS_MD_EXTRACTOR = False


def extract_text_from_file(content: bytes, extension: str) -> str:
    """Extract text from uploaded bytes (PDF first, images later)."""
    text, _meta = extract_text_from_file_with_meta(content, extension)
    return text


def extract_text_from_file_with_meta(content: bytes, extension: str) -> tuple[str, dict[str, Any]]:
    """Extract text + debug metadata."""
    extraction_meta: dict[str, Any] = {
        "extension": extension.lower().strip("."),
        "method": "unknown",
        "ocr_engine": None,
        "ocr_strategy": None,
    }
    text = _extract_text_from_file_raw(content, extension, extraction_meta=extraction_meta)
    return postgres_safe_text(text), extraction_meta


def _extract_text_from_file_raw(
    content: bytes, extension: str, extraction_meta: dict[str, Any]
) -> str:
    extension = extension.lower().strip(".")

    if extension == "pdf":
        return _extract_pdf_text(content, extraction_meta)

    if extension in ["png", "jpg", "jpeg", "tiff", "tif"]:
        return _extract_image_text(content, extension, extraction_meta)

    return _extract_plain_text(content, extraction_meta)


def _extract_pdf_text(content: bytes, meta: dict[str, Any]) -> str:
    from app.config import get_settings
    settings = get_settings()
    page_markers = bool(settings.PDF_PAGE_MARKERS)
    
    ext_text = ""
    
    # 1. Structured extraction (Markdown)
    if HAS_MD_EXTRACTOR:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            ext_text = pymupdf4llm.to_markdown(tmp_path)
        except Exception as e:
            logger.error("pymupdf4llm_failed", error=str(e))
        finally:
            os.unlink(tmp_path)

    # 2. Native text fallback
    if not ext_text or not str(ext_text).strip():
        try:
            text_chunks = []
            with fitz.open(stream=content, filetype="pdf") as doc:
                for i, page in enumerate(doc):
                    raw = page.get_text("text")
                    if page_markers:
                        text_chunks.append(f"---PAGE {i + 1}---\n{raw}")
                    else:
                        text_chunks.append(raw)
            ext_text = "\n".join(text_chunks)
        except Exception as e:
            logger.warning("native_pdf_text_extraction_failed", error=str(e))

    ext_text = str(ext_text).strip()

    # 3. Add page count prefix if missing
    if ext_text and "---PAGE " not in ext_text[:4000] and page_markers:
        try:
            with fitz.open(stream=content, filetype="pdf") as doc:
                npages = len(doc)
            if npages > 0:
                ext_text = f"---PDF {npages} PAGES---\n\n" + ext_text
        except Exception:
            pass

    # 4. OCR Fallback for scanned PDFs
    if len(ext_text.split()) < 10:
        try:
            ocr_dpi = getattr(settings, "OCR_DPI", 300)
            ocr_lang = getattr(settings, "OCR_LANG", "fra+eng")
            ocr_engine = getattr(settings, "OCR_ENGINE", "auto")
            ocr_text, selected_engine = extract_pdf_text_via_ocr_engines(
                content,
                dpi=ocr_dpi,
                lang=ocr_lang,
                page_markers=page_markers,
                engine=str(ocr_engine),
            )
            if ocr_text:
                meta["method"] = "ocr_pdf_fallback"
                meta["ocr_strategy"] = str(ocr_engine)
                meta["ocr_engine"] = selected_engine
                return ocr_text
        except Exception as exc:
            logger.warning("ocr_pdf_fallback_failed", error=str(exc))

    meta["method"] = "native_pdf_pymupdf"
    return ext_text


def _extract_image_text(content: bytes, extension: str, meta: dict[str, Any]) -> str:
    if not HAS_PIL:
        return ""
        
    try:
        from app.config import get_settings
        settings = get_settings()
        ocr_lang = getattr(settings, "OCR_LANG", "fra+eng")
        img = Image.open(BytesIO(content))

        if extension in ["tiff", "tif"]:
            ocr_chunks = []
            frame_idx = 0
            try:
                while True:
                    img.seek(frame_idx)
                    chunk = ocr_image(img.copy(), lang=ocr_lang)
                    if chunk:
                        ocr_chunks.append(f"---PAGE {frame_idx + 1}---\n{chunk}")
                    frame_idx += 1
            except EOFError:
                pass
            if ocr_chunks:
                meta["method"] = "ocr_tesseract_tiff_enhanced"
                meta["ocr_engine"] = "tesseract"
                return "\n".join(ocr_chunks).strip()

        result = ocr_image(img, lang=ocr_lang)
        meta["method"] = "ocr_tesseract_image_enhanced"
        meta["ocr_engine"] = "tesseract"
        return result
    except Exception as exc:
        logger.warning("ocr_image_failed", extension=extension, error=str(exc))
        return ""


def _extract_plain_text(content: bytes, meta: dict[str, Any]) -> str:
    meta["method"] = "fallback_plain_text"
    try:
        return content.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""
