"""ConfiDoc Backend — OCR Engines Service."""

import re
from functools import lru_cache
from typing import Any

from app.core.logging import get_logger
from app.services.ocr.preprocessing import preprocess_image_for_ocr

logger = get_logger(__name__)

try:
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    from doctr.io import DocumentFile as DoctrDocumentFile
    from doctr.models import ocr_predictor as doctr_ocr_predictor
    HAS_DOCTR = True
except ImportError:
    HAS_DOCTR = False


def get_tesseract_config() -> str:
    """Build optimal Tesseract configuration string."""
    # --oem 3: LSTM + legacy combined engine (best accuracy)
    # --psm 6: Assume uniform block of text (best for scanned docs)
    # preserve_interword_spaces: keep spacing for table-heavy docs
    return "--oem 3 --psm 6 -c preserve_interword_spaces=1"


def ocr_image(img: "Image.Image", lang: str = "fra+eng") -> str:
    """Run Tesseract OCR on a single image with preprocessing and optimal config."""
    if not HAS_OCR:
        return ""
    processed = preprocess_image_for_ocr(img)
    config = get_tesseract_config()
    return str(pytesseract.image_to_string(processed, lang=lang, config=config)).strip()


@lru_cache(maxsize=1)
def get_doctr_model():
    if not HAS_DOCTR:
        raise RuntimeError("docTR not installed")
    return doctr_ocr_predictor(pretrained=True)


def ocr_with_doctr_pdf(content: bytes, page_markers: bool) -> str:
    """Run docTR OCR on a PDF and return page-concatenated text."""
    if not HAS_DOCTR:
        return ""
    model = get_doctr_model()
    doc = DoctrDocumentFile.from_pdf(content)
    result = model(doc)
    payload = result.export()
    pages_out: list[str] = []
    for i, page in enumerate(payload.get("pages", []), start=1):
        lines: list[str] = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = [w.get("value", "") for w in line.get("words", []) if w.get("value")]
                if words:
                    lines.append(" ".join(words))
        page_text = "\n".join(lines).strip()
        if page_markers:
            pages_out.append(f"---PAGE {i}---\n{page_text}")
        else:
            pages_out.append(page_text)
    return "\n".join(pages_out).strip()


def score_ocr_text_candidate(text: str) -> int:
    """Simple robustness score to pick better OCR text candidate."""
    if not text:
        return 0
    words = len(text.split())
    digits = len(re.findall(r"\d", text))
    tables = len(
        re.findall(r"\b(total|résultat|resultat|passif|actif|revenus?)\b", text, re.IGNORECASE)
    )
    return (words * 2) + digits + (tables * 10)


def extract_pdf_text_via_ocr_engines(
    content: bytes, *, dpi: int, lang: str, page_markers: bool, engine: str
) -> tuple[str, str]:
    """Extract OCR text with selected strategy (tesseract/doctr/auto)."""
    candidates: list[tuple[str, str]] = []

    # Tesseract candidate
    if engine in ("auto", "tesseract") and HAS_OCR:
        try:
            images = convert_from_bytes(content, dpi=dpi)
            chunks: list[str] = []
            for i, img in enumerate(images):
                chunk = ocr_image(img, lang=lang)
                chunks.append(f"---PAGE {i + 1}---\n{chunk}" if page_markers else chunk)
            candidates.append(("tesseract", "\n".join(chunks).strip()))
        except Exception as exc:
            logger.warning("ocr_tesseract_failed", extension="pdf", error=str(exc))

    # docTR candidate
    if engine in ("auto", "doctr") and HAS_DOCTR:
        try:
            txt = ocr_with_doctr_pdf(content, page_markers=page_markers)
            candidates.append(("doctr", txt))
        except Exception as exc:
            logger.warning("ocr_doctr_failed", extension="pdf", error=str(exc))

    if not candidates:
        return "", ""

    method, best_text = max(candidates, key=lambda c: score_ocr_text_candidate(c[1]))
    logger.info("document_extraction", method=f"ocr_{method}_pdf", extension="pdf")
    return best_text, method
