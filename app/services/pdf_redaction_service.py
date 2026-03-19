"""ConfiDoc Backend — Visual PDF redaction service."""

import fitz


def redact_pdf_bytes(original_pdf: bytes, sensitive_values: list[str]) -> bytes:
    """Apply visual black redactions on a PDF for provided values."""
    cleaned_values = [v.strip() for v in sensitive_values if v and v.strip()]
    if not cleaned_values:
        return original_pdf

    doc = fitz.open(stream=original_pdf, filetype="pdf")
    try:
        for page in doc:
            for value in cleaned_values:
                areas = page.search_for(value)
                for rect in areas:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()

        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()
