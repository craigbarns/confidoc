"""ConfiDoc Backend — Entity Detection Logic."""

import re
from typing import Any

from app.core.tokens import TOKEN_REDACTED
from app.services.anonymization.patterns import (
    ACCOUNTING_GUARD_PATTERNS,
    BIC_LABELED_PATTERN,
    FALSE_POSITIVE_WORDS,
    LABEL_VALUE_PATTERN,
    PATTERNS,
    QUASI_IDENTIFIER_PATTERNS,
    STRICT_ONLY_PATTERNS,
)


def is_false_positive(value: str) -> bool:
    """Check if an extracted value is a known false positive."""
    clean = value.strip().upper()
    # Exact match
    if clean in FALSE_POSITIVE_WORDS:
        return True
    # All words are false positives
    words = clean.split()
    if words and all(w in FALSE_POSITIVE_WORDS for w in words):
        return True
    # Too short
    if len(clean) < 3:
        return True
    
    return any(re.search(pat, clean) for pat in ACCOUNTING_GUARD_PATTERNS)


def detect_entities(
    text: str, profile: str = "moderate", document_type: str = "generic"
) -> list[dict[str, Any]]:
    """Core entity detection engine."""
    matches: list[dict[str, Any]] = []

    # ── Base patterns (always applied) ──
    for entity_type, pattern, replacement in PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if is_false_positive(value):
                continue
            matches.append(
                {
                    "entity_type": entity_type,
                    "start_index": match.start(),
                    "end_index": match.end(),
                    "value_excerpt": value,
                    "replacement": replacement,
                }
            )

    # ── Label:Value detection (always applied) ──
    for match in LABEL_VALUE_PATTERN.finditer(text):
        value = match.group(1).strip()
        if not value or is_false_positive(value):
            continue
        matches.append(
            {
                "entity_type": "labeled_sensitive_value",
                "start_index": match.start(1),
                "end_index": match.end(1),
                "value_excerpt": value,
                "replacement": "[REDACTED]",
            }
        )

    # ── BIC detection only when explicitly labeled (avoid false positives) ──
    for match in BIC_LABELED_PATTERN.finditer(text):
        value = match.group(1).strip()
        if not value or is_false_positive(value):
            continue
        matches.append(
            {
                "entity_type": "bic",
                "start_index": match.start(1),
                "end_index": match.end(1),
                "value_excerpt": value,
                "replacement": "[BIC]",
            }
        )

    # ── Strict-only patterns ──
    is_strict = profile in {
        "strict",
        "dataset_strict",
        "dataset_accounting",
        "dataset_accounting_pseudo",
    }
    if is_strict:
        for entity_type, pattern, replacement in STRICT_ONLY_PATTERNS:
            # Dataset accounting: keep amounts for business utility
            if profile in {"dataset_accounting", "dataset_accounting_pseudo"} and entity_type in {
                "amount_eur",
                "amount_plain",
            }:
                continue

            for match in pattern.finditer(text):
                value = match.group(0)
                if is_false_positive(value):
                    continue

                rep = replacement
                # Bank account: keep code in accounting mode
                if entity_type == "bank_account_code_label":
                    code = match.group(1)
                    rep = (
                        f"{code} [REDACTED]"
                        if profile in {"dataset_accounting", "dataset_accounting_pseudo"}
                        else "[REDACTED]"
                    )

                matches.append(
                    {
                        "entity_type": entity_type,
                        "start_index": match.start(),
                        "end_index": match.end(),
                        "value_excerpt": value,
                        "replacement": rep,
                    }
                )

        # ── Identity block heuristic (invoice/accounting header zone) ──
        if document_type in {"invoice", "accounting", "generic"}:
            _detect_identity_block(text, matches)

    # ── Quasi-identifier patterns (always applied in strict, optional in moderate) ──
    if is_strict or profile == "moderate":
        for entity_type, pattern, replacement in QUASI_IDENTIFIER_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(0)
                if is_false_positive(value):
                    continue
                matches.append(
                    {
                        "entity_type": entity_type,
                        "start_index": match.start(),
                        "end_index": match.end(),
                        "value_excerpt": value,
                        "replacement": replacement,
                    }
                )

    # ── De-duplicate with longest-match priority ──
    return deduplicate(matches)


def _detect_identity_block(text: str, matches: list[dict[str, Any]]) -> None:
    """Detect and add identity block lines from invoice/accounting headers."""
    # Find header zone: before "désignation", or first 1200 chars
    desig_idx = text.lower().find("désignation")
    if desig_idx < 0:
        desig_idx = text.lower().find("designation")
    header_zone = text[:desig_idx] if desig_idx > 0 else text[:1200]

    for line in header_zone.splitlines():
        clean = line.strip()
        if not clean or len(clean) < 6:
            continue
        if is_false_positive(clean):
            continue

        upper_count = sum(c.isupper() for c in clean)
        has_digits = any(ch.isdigit() for ch in clean)

        looks_identity = (
            # Legal form keywords
            any(kw in clean.lower() for kw in ("sci", "sas", "sarl", "eurl", "selarl"))
            # Address keywords
            or any(
                kw in clean.lower()
                for kw in ("terrasses", "rue", "avenue", "boulevard", "résidence")
            )
            # Two+ capitalized words (person name pattern)
            or re.search(
                r"\b[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]{2,}\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]{2,}\b",
                clean,
            )
            is not None
            # Heavy uppercase non-digit line (likely a name/company)
            or (upper_count >= max(5, int(len(clean) * 0.5)) and not has_digits)
        )

        if not looks_identity:
            continue

        start = text.find(line)
        if start < 0:
            continue
        end = start + len(line)
        matches.append(
            {
                "entity_type": "invoice_identity_block",
                "start_index": start,
                "end_index": end,
                "value_excerpt": line,
                "replacement": "[IDENTITY]",
            }
        )


def deduplicate(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep longest match first, then left-to-right, remove overlaps."""
    matches.sort(key=lambda m: (m["start_index"], -(m["end_index"] - m["start_index"])))
    kept: list[dict[str, Any]] = []
    for candidate in matches:
        overlap = any(
            not (
                candidate["end_index"] <= item["start_index"]
                or candidate["start_index"] >= item["end_index"]
            )
            for item in kept
        )
        if not overlap:
            kept.append(candidate)
    return kept
