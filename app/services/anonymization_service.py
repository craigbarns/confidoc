"""ConfiDoc Backend — Text extraction and anonymization service."""

import re

import fitz

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    ("phone_fr", re.compile(r"\b(?:\+33|0)[1-9](?:[\s\.-]?\d{2}){4}\b"), "[PHONE]"),
    ("phone_intl", re.compile(r"\+\d{1,3}[\s\.-]?\d(?:[\s\.-]?\d){6,14}\b"), "[PHONE]"),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[IBAN]"),
    ("bic", re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?\b"), "[BIC]"),
    ("siren", re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\b"), "[SIREN]"),
    ("siret", re.compile(r"\b\d{3}\s?\d{3}\s?\d{3}\s?\d{5}\b"), "[SIRET]"),
    ("vat_fr", re.compile(r"\bFR\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b"), "[VAT]"),
    (
        "address_line",
        re.compile(
            r"\b\d{1,4}\s+(?:rue|avenue|av\.?|boulevard|bd|chemin|impasse|allée|allee|place|quai|route)\s+[^\n,]{3,}",
            re.IGNORECASE,
        ),
        "[ADDRESS]",
    ),
    ("postal_city", re.compile(r"\b\d{5}\s+[A-Za-zÀ-ÖØ-öø-ÿ'’\- ]{2,}\b"), "[CITY]"),
    (
        "person_title",
        re.compile(
            r"\b(?:M\.?|Monsieur|Mme|Madame)\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+){0,2}\b"
        ),
        "[PERSON]",
    ),
]

LABEL_VALUE_PATTERN = re.compile(
    r"(?im)^(?:nom|prénom|prenom|raison\s+sociale|société|societe|client|destinataire|titulaire|bénéficiaire|beneficiaire|adresse|email|mail|téléphone|telephone|tel|mobile|iban|bic|siret|siren|tva(?:\s+intracom)?|n[°o]\s*client)\s*[:\-]\s*(.+)$"
)


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


def _detect_entities(text: str) -> list[dict]:
    matches: list[dict] = []
    for entity_type, pattern, replacement in PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            matches.append(
                {
                    "entity_type": entity_type,
                    "start_index": match.start(),
                    "end_index": match.end(),
                    "value_excerpt": value,
                    "replacement": replacement,
                }
            )

    for match in LABEL_VALUE_PATTERN.finditer(text):
        value = match.group(1).strip()
        if not value:
            continue
        start = match.start(1)
        end = match.end(1)
        matches.append(
            {
                "entity_type": "labeled_sensitive_value",
                "start_index": start,
                "end_index": end,
                "value_excerpt": value,
                "replacement": "[REDACTED]",
            }
        )

    # Keep longest match first, then left-to-right
    matches.sort(key=lambda m: (m["start_index"], -(m["end_index"] - m["start_index"])))
    kept: list[dict] = []
    for candidate in matches:
        overlap = False
        for item in kept:
            if not (
                candidate["end_index"] <= item["start_index"]
                or candidate["start_index"] >= item["end_index"]
            ):
                overlap = True
                break
        if not overlap:
            kept.append(candidate)

    return kept


def anonymize_text(text: str) -> tuple[str, list[dict]]:
    """Apply regex-based anonymization and return detections metadata."""
    detections = _detect_entities(text)
    anonymized = text
    for match in sorted(detections, key=lambda m: m["start_index"], reverse=True):
        start = match["start_index"]
        end = match["end_index"]
        anonymized = anonymized[:start] + match["replacement"] + anonymized[end:]
    return anonymized, detections
