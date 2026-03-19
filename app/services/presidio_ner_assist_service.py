"""ConfiDoc Backend — Presidio assistif local (PII local/offline)."""

from __future__ import annotations

from typing import Any

import re

from presidio_analyzer import AnalyzerEngine

from app.config import get_settings

settings = get_settings()

_ANALYZER = AnalyzerEngine()

ALLOWED_REPLACEMENT_TOKENS: set[str] = {
    "[EMAIL]",
    "[PHONE]",
    "[IBAN]",
    "[BIC]",
    "[SIREN]",
    "[SIRET]",
    "[VAT]",
    "[COMPANY]",
    "[PERSON]",
    "[ADDRESS]",
    "[CITY]",
    "[DATE]",
    "[AMOUNT]",
    "[INVOICE_REF]",
    "[REDACTED]",
    "[COUNTRY]",
    "[IDENTITY]",
}


def _replacement_for_presidio(entity_type: str, entity_text: str) -> str | None:
    et = (entity_type or "").upper()
    if et == "EMAIL_ADDRESS":
        return "[EMAIL]"
    if et == "PHONE_NUMBER":
        return "[PHONE]"
    if et == "IBAN_CODE":
        return "[IBAN]"
    if et == "PERSON":
        return "[PERSON]"
    if et == "LOCATION":
        # Heuristique adresse vs ville
        if re.search(r"\b\d{1,4}\b", entity_text) or re.search(
            r"\b(rue|avenue|bd|boulevard|chemin|place|quai|route)\b",
            entity_text,
            flags=re.IGNORECASE,
        ):
            return "[ADDRESS]"
        return "[CITY]"
    if et in {"DATE_TIME"}:
        return "[DATE]"
    return None


async def propose_spans_presidio(snippet_text: str) -> list[dict[str, Any]]:
    """Propose des spans (start/end relatifs au snippet) via Presidio local."""
    # Presidio est offline: aucune donnée n'est envoyée.
    if not snippet_text or not settings.LLM_ASSISTIVE_ENABLED:
        return []

    try:
        # entities = types que nous savons mapper vers tokens ConfiDoc.
        entities = ["PERSON", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER", "IBAN_CODE", "DATE_TIME"]
        results = _ANALYZER.analyze(
            text=snippet_text,
            language="fr",
            entities=entities,
            score_threshold=0.35,
        )
    except Exception:
        return []

    spans: list[dict[str, Any]] = []
    for r in results:
        try:
            start = int(r.start)
            end = int(r.end)
            entity_type = str(r.entity_type)
            entity_text = snippet_text[start:end]
            replacement = _replacement_for_presidio(entity_type, entity_text)
            if not replacement or replacement not in ALLOWED_REPLACEMENT_TOKENS:
                continue
            if end <= start:
                continue
            spans.append(
                {
                    "entity_type": replacement.strip("[]").lower(),
                    "start": start,
                    "end": end,
                    "replacement_token": replacement,
                    "confidence": float(getattr(r, "score", 0.0) or 0.0),
                }
            )
        except Exception:
            continue

    return spans

