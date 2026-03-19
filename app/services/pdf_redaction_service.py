"""ConfiDoc Backend — Visual PDF redaction service (v2)."""

import re
import fitz

from app.core.logging import get_logger

logger = get_logger(__name__)


def redact_pdf_bytes(original_pdf: bytes, sensitive_values: list[str]) -> bytes:
    """Apply visual black redactions on a PDF for the provided sensitive values.

    Returns the redacted PDF bytes.
    """
    cleaned_values = [v.strip() for v in sensitive_values if v and v.strip() and len(v.strip()) >= 3]
    if not cleaned_values:
        return original_pdf

    def normalize(s: str) -> str:
        s = s.replace("\u00a0", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def candidates_for_value(v: str) -> set[str]:
        """Generate robust search candidates for a sensitive value.

        PDF text may have different whitespace/hyphenation than extracted text,
        so we generate multiple search variants.
        """
        v_norm = normalize(v)
        cands: set[str] = set()
        if not v_norm:
            return cands

        # Full normalized value + uppercase
        cands.add(v_norm)
        upper = v_norm.upper()
        if upper != v_norm:
            cands.add(upper)

        # Significant tokens (length >= 4)
        tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]{3,}", v_norm)
        for t in tokens:
            if len(t) >= 4:
                cands.add(t)
                cands.add(t.upper())

        # Multi-word: try first+second and last two words
        if " " in v_norm:
            parts = [p for p in v_norm.split(" ") if p]
            if len(parts) >= 2:
                cands.add(f"{parts[0]} {parts[1]}")
                cands.add(f"{parts[-2]} {parts[-1]}")

        # Numeric-heavy values (SIRET/SIREN): search digits only
        digits = re.sub(r"\D+", "", v_norm)
        if len(digits) >= 5:
            cands.add(digits)
            # Also try with spaces between groups of 3
            if len(digits) >= 9:
                spaced = " ".join(digits[i:i + 3] for i in range(0, len(digits), 3))
                cands.add(spaced)

        return cands

    doc = fitz.open(stream=original_pdf, filetype="pdf")
    total_redactions = 0
    try:
        for page in doc:
            page_redactions = 0
            for value in cleaned_values:
                for cand in candidates_for_value(value):
                    if len(cand) < 3:
                        continue
                    try:
                        areas = page.search_for(cand)
                    except Exception:
                        continue
                    for rect in areas:
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                        page_redactions += 1
            if page_redactions > 0:
                page.apply_redactions()
                total_redactions += page_redactions

        logger.info("pdf_redaction_complete", total_redactions=total_redactions)
        return doc.tobytes(garbage=4, deflate=True)
    finally:
        doc.close()
