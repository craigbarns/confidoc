"""ConfiDoc Backend — Text extraction and anonymization service."""

import re

import fitz

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    ("phone", re.compile(r"\b(?:\+33|0)[1-9](?:[\s\.-]?\d{2}){4}\b"), "[PHONE]"),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[IBAN]"),
    ("siren", re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\b"), "[SIREN]"),
]


def extract_text_from_file(content: bytes, extension: str) -> str:
    """Extract text from uploaded bytes (PDF first)."""
    extension = extension.lower()
    if extension == "pdf":
        text_chunks: list[str] = []
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page in doc:
                text_chunks.append(page.get_text("text"))
        return "\n".join(text_chunks).strip()

    # Fallback minimal for non-PDF files in V1.
    try:
        return content.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def anonymize_text(text: str) -> tuple[str, list[dict]]:
    """Apply regex-based anonymization and return detections metadata."""
    detections: list[dict] = []
    anonymized = text

    for entity_type, pattern, replacement in PATTERNS:
        matches = list(pattern.finditer(anonymized))
        for match in matches:
            detections.append(
                {
                    "entity_type": entity_type,
                    "start_index": match.start(),
                    "end_index": match.end(),
                    "value_excerpt": match.group(0),
                    "replacement": replacement,
                }
            )
        anonymized = pattern.sub(replacement, anonymized)

    return anonymized, detections
