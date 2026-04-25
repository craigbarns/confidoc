"""ConfiDoc Backend — Entity Detection Logic."""

import re
from typing import Any

from app.core.tokens import TOKEN_DATE_NAISSANCE, TOKEN_PERSONNE, TOKEN_SOCIETE
from app.services.anonymization.patterns import (
    ACCOUNTING_GUARD_PATTERNS,
    BIC_LABELED_PATTERN,
    FALSE_POSITIVE_WORDS,
    LABEL_VALUE_PATTERN,
    PATTERNS,
    QUASI_IDENTIFIER_PATTERNS,
    STRICT_ONLY_PATTERNS,
)

ACCOUNTING_DOCUMENT_TYPES = {
    "auto",
    "generic",
    "accounting",
    "financial_statement",
    "tax_return",
}

ACCOUNTING_SECTION_HINT_RE = re.compile(
    r"(?i)\b(?:plaquette|bilan|passif|actif|compte\s+de\s+r[ée]sultat|"
    r"soldes\s+interm[ée]diaires|liasse|d[ée]claration|imp[ôo]t|filiales|"
    r"participations|capital\s+social|entreprise\s+d[ée]clarante|"
    r"expert[\-\s]?comptable|comptable|siret|siren)\b"
)
ACCOUNTING_PERSON_ACCOUNT_RE = re.compile(
    r"\b(?P<code>(?:421[A-Z0-9]*|455\d{3,6}))\s+"
    r"(?P<name>[A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý' \-]{2,80}?)"
    r"(?=\s+-\s*(?:SALAIRE|COMPTE\s+COURANT|REMUNERATION|R[ÉE]MUN[ÉE]RATION)\b)"
)
ACCOUNTING_COMPANY_ACCOUNT_RE = re.compile(
    r"\b(?P<code>451\d{5})\s+"
    r"(?P<name>[A-Z0-9][A-Z0-9&' \-]{2,60}?)(?=\s+\d|[ \t]*\||[ \t]*$)"
)
LEGAL_DENOMINATION_RE = re.compile(
    r"(?i)\bd[ée]nomination\s+"
    r"(?P<name>[A-ZÀ-ÖØ-Ý0-9][A-ZÀ-ÖØ-Ý0-9&' \-]{2,60})"
    r"(?=\s+(?:\[|SIREN|N[°o]|%|\||$))"
)
CAPITAL_HOLDER_RE = re.compile(
    r"(?i)\bNom\s+complet\s*\|\s*(?P<name>[^|\n]{3,80}?)(?=\s*\|)"
)
BIRTH_TABLE_DATE_RE = re.compile(
    r"(?i)\bNaissance\s*:\s*\|\s*Date\s*\|\s*"
    r"(?P<date>\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})"
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

    if document_type in ACCOUNTING_DOCUMENT_TYPES:
        _detect_accounting_sensitive_values(text, matches)

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
                if entity_type in {"person_name", "person_uppercase"} and re.match(
                    r"(?i)\b(?:d[ée]nomination|nom\s+complet|naissance)\b",
                    value,
                ):
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
        if document_type in {
            "auto",
            "invoice",
            "accounting",
            "generic",
            "financial_statement",
            "tax_return",
        }:
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


def _add_match(
    matches: list[dict[str, Any]],
    *,
    entity_type: str,
    start_index: int,
    end_index: int,
    value_excerpt: str,
    replacement: str,
) -> None:
    if not value_excerpt.strip() or is_false_positive(value_excerpt):
        return
    matches.append(
        {
            "entity_type": entity_type,
            "start_index": start_index,
            "end_index": end_index,
            "value_excerpt": value_excerpt,
            "replacement": replacement,
        }
    )


def _line_positions(text: str) -> list[tuple[int, int, str]]:
    positions: list[tuple[int, int, str]] = []
    start = 0
    for line in text.splitlines(keepends=True):
        raw = line.rstrip("\r\n")
        end = start + len(raw)
        positions.append((start, end, raw))
        start += len(line)
    return positions


def _is_sensitive_accounting_heading(clean: str, context: str) -> bool:
    normalized = clean.strip(" \t|#*")
    if len(normalized) < 5 or len(normalized) > 45:
        return False
    if any(ch.isdigit() for ch in normalized):
        return False
    if is_false_positive(normalized):
        return False
    letters = [ch for ch in normalized if ch.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(ch.isupper() for ch in letters) / len(letters)
    if upper_ratio < 0.72:
        return False
    return ACCOUNTING_SECTION_HINT_RE.search(context) is not None


def _add_all_occurrences(
    text: str,
    matches: list[dict[str, Any]],
    *,
    entity_type: str,
    value: str,
    replacement: str,
) -> None:
    escaped = re.escape(value)
    pattern = re.compile(rf"(?<![A-Za-zÀ-ÖØ-öø-ÿ0-9]){escaped}(?![A-Za-zÀ-ÖØ-öø-ÿ0-9])")
    for match in pattern.finditer(text):
        _add_match(
            matches,
            entity_type=entity_type,
            start_index=match.start(),
            end_index=match.end(),
            value_excerpt=match.group(0),
            replacement=replacement,
        )


def _detect_accounting_sensitive_values(text: str, matches: list[dict[str, Any]]) -> None:
    """Catch accounting-package leaks that survive generic PII regexes."""
    for pattern, entity_type, replacement in (
        (ACCOUNTING_PERSON_ACCOUNT_RE, "accounting_person_account_label", TOKEN_PERSONNE),
        (ACCOUNTING_COMPANY_ACCOUNT_RE, "accounting_company_account_label", TOKEN_SOCIETE),
        (LEGAL_DENOMINATION_RE, "legal_denomination", TOKEN_SOCIETE),
        (CAPITAL_HOLDER_RE, "capital_holder_name", TOKEN_PERSONNE),
        (BIRTH_TABLE_DATE_RE, "birth_table_date", TOKEN_DATE_NAISSANCE),
    ):
        for match in pattern.finditer(text):
            group_name = "date" if entity_type == "birth_table_date" else "name"
            value = match.group(group_name).strip()
            _add_match(
                matches,
                entity_type=entity_type,
                start_index=match.start(group_name),
                end_index=match.end(group_name),
                value_excerpt=value,
                replacement=replacement,
            )

    lines = _line_positions(text)
    sensitive_terms: set[str] = set()
    for index, (start, _end, line) in enumerate(lines):
        clean = line.strip()
        if not clean:
            continue
        previous_lines = [item[2].strip() for item in lines[max(0, index - 3):index]]
        next_lines = [item[2].strip() for item in lines[index + 1:index + 4]]
        context = "\n".join([*previous_lines, clean, *next_lines])
        if not _is_sensitive_accounting_heading(clean, context):
            continue

        value = clean.strip(" \t|#*")
        offset = line.find(value)
        if offset < 0:
            continue
        sensitive_terms.add(value)
        _add_match(
            matches,
            entity_type="accounting_identity_heading",
            start_index=start + offset,
            end_index=start + offset + len(value),
            value_excerpt=value,
            replacement=TOKEN_SOCIETE,
        )

    for term in sensitive_terms:
        _add_all_occurrences(
            text,
            matches,
            entity_type="accounting_identity_repeat",
            value=term,
            replacement=TOKEN_SOCIETE,
        )


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
        lowered = clean.lower()
        if "|" in clean or lowered.startswith(("dénomination", "denomination")):
            continue
        if re.match(r"^(?:\d{3,}|421[A-Z0-9]+)", clean):
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
