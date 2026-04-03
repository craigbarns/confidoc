"""ConfiDoc — Docling document parsing service.

Uses docling-project/docling for advanced PDF/document understanding:
- Table extraction with structure
- Section/heading detection
- Multi-format support (PDF, DOCX, PPTX, images)
- Markdown export with document structure preserved

Falls back to Mistral OCR if Docling fails (e.g. scanned-only PDFs
with no text layer).
"""

from __future__ import annotations

import io
import tempfile
import os
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


def _convert_sync(file_content: bytes, extension: str) -> dict[str, Any]:
    """Run Docling conversion synchronously (CPU-bound).

    Returns a dict with:
      - text: full markdown text
      - tables: list of extracted tables as markdown
      - sections: list of {level, title} headings
      - pages: estimated page count
      - method: "docling"
    """
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    suffix = f".{extension.lower().lstrip('.')}"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(file_content)
        tmp.flush()
        tmp.close()

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False  # Mistral OCR handles this already

        converter = DocumentConverter(
            format_options={
                "pdf": PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        result = converter.convert(tmp.name)
        doc = result.document

        md_text = doc.export_to_markdown()

        tables: list[str] = []
        sections: list[dict[str, Any]] = []

        for item in doc.tables:
            try:
                tbl_md = item.export_to_markdown(doc=doc)
                if tbl_md and tbl_md.strip():
                    tables.append(tbl_md.strip())
            except Exception:
                try:
                    tbl_md = item.export_to_markdown()
                    if tbl_md and tbl_md.strip():
                        tables.append(tbl_md.strip())
                except Exception:
                    pass

        for item in doc.texts:
            try:
                label = getattr(item, "label", None)
                if label and "heading" in str(label).lower():
                    level_str = str(label).lower().replace("heading", "").replace("_", "").strip()
                    level = int(level_str) if level_str.isdigit() else 1
                    sections.append({"level": level, "title": item.text.strip()})
            except Exception:
                pass

        page_count = 0
        try:
            page_count = len(doc.pages) if hasattr(doc, "pages") else 0
        except Exception:
            pass

        logger.info(
            "docling_conversion_complete",
            chars=len(md_text),
            tables=len(tables),
            sections=len(sections),
            pages=page_count,
        )

        return {
            "text": md_text,
            "tables": tables,
            "sections": sections,
            "pages": page_count,
            "method": "docling",
            "error": None,
        }

    except Exception as exc:
        logger.error("docling_conversion_failed", error=str(exc), error_type=type(exc).__name__)
        return {
            "text": "",
            "tables": [],
            "sections": [],
            "pages": 0,
            "method": "docling",
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
        }
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


async def extract_with_docling(
    file_content: bytes,
    extension: str = "pdf",
) -> dict[str, Any]:
    """Async wrapper — runs Docling in a thread to avoid blocking the event loop."""
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _convert_sync, file_content, extension)


async def extract_text_from_file_docling(
    file_content: bytes,
    extension: str = "pdf",
) -> tuple[str, dict[str, Any]]:
    """Drop-in replacement for mistral_ocr_service.extract_text_from_file.

    Tries Docling first. If it fails or returns empty text, falls back
    to Mistral OCR.

    Returns:
        (text, metadata_dict)
    """
    docling_result = await extract_with_docling(file_content, extension)

    if docling_result["text"].strip() and not docling_result.get("error"):
        meta = {
            "extension": extension,
            "method": "docling",
            "pages": docling_result["pages"],
            "tables_count": len(docling_result["tables"]),
            "sections_count": len(docling_result["sections"]),
        }
        return docling_result["text"], meta

    logger.info("docling_fallback_to_mistral_ocr", reason=docling_result.get("error", "empty_text"))
    from app.services.mistral_ocr_service import extract_text_from_file
    text, ocr_meta = await extract_text_from_file(file_content, extension)
    ocr_meta["docling_attempted"] = True
    ocr_meta["docling_error"] = docling_result.get("error")
    return text, ocr_meta


async def get_structured_content(
    file_content: bytes,
    extension: str = "pdf",
) -> dict[str, Any]:
    """Extract structured content (tables, sections) for enriching the review agent.

    This is called separately from text extraction so the agent gets
    both the full text AND the structured elements.
    """
    result = await extract_with_docling(file_content, extension)

    if result.get("error"):
        return {"tables": [], "sections": [], "available": False}

    return {
        "tables": result["tables"][:20],
        "sections": result["sections"][:50],
        "available": True,
    }
