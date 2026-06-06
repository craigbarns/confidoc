"""AI Firewall — residual-PII detection, risk scoring, verdict and redaction.

This module is deterministic and dependency-light. It reuses the existing
anonymization regex patterns (single source of truth) instead of duplicating
them, so the firewall stays in sync with the anonymization engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.tokens import TOKEN_PERSONNE, TOKEN_SIRET
from app.services.anonymization.detector import is_false_positive
from app.services.anonymization.patterns import PATTERNS

# ── Verdicts ────────────────────────────────────────────────────────────
ALLOW = "allow"
REDACT = "redact"
BLOCK = "block"

# ── Severity per entity type ────────────────────────────────────────────
# critical: direct financial / identity identifiers — reidentification on their own
# high:     strong direct identifiers
# medium:   quasi-identifiers
_SEVERITY: dict[str, str] = {
    "NSS": "critical",
    "IBAN": "critical",
    "EMAIL": "high",
    "TELEPHONE": "high",
    "SIRET": "high",
    "SIREN": "medium",
    "TVA": "medium",
    "ADRESSE": "medium",
    "VILLE": "medium",
    "PERSONNE": "medium",
}

_SEVERITY_WEIGHT: dict[str, float] = {
    "critical": 50.0,
    "high": 25.0,
    "medium": 10.0,
}

# Maps the reused anonymization pattern *name* -> firewall entity type.
# Order matters: most specific / longest matches first so a phone number is not
# mislabelled as a SIREN, an IBAN is not split into amounts, etc. Matched spans
# are replaced by their token as we go, preventing double counting.
_PATTERN_NAME_TO_TYPE: list[tuple[str, str]] = [
    ("nss", "NSS"),
    ("iban", "IBAN"),
    ("iban_compact", "IBAN"),
    ("vat_fr", "TVA"),
    ("siret_ocr_labeled", "SIRET"),
    ("siret", "SIRET"),
    ("phone_fr", "TELEPHONE"),
    ("phone_intl", "TELEPHONE"),
    ("email", "EMAIL"),
    ("siren", "SIREN"),
    ("person_title", "PERSONNE"),
    ("person_name_common", "PERSONNE"),
    ("person_uppercase_labeled", "PERSONNE"),
    ("address_line", "ADRESSE"),
    ("postal_city", "VILLE"),
]

_COMMON_FIRST_NAMES_RE = (
    r"Alexandre|Alexis|Alice|Amandine|Anais|Anaïs|André|Anne|Antoine|Arthur|Camille|"
    r"Caroline|Catherine|Charlotte|Chloé|Claire|Clément|David|Emilie|Émilie|Emma|"
    r"Eric|Éric|François|Gabriel|Gregory|Grégory|Guillaume|Hugo|Isabelle|Jacques|"
    r"Jean|Julie|Julien|Laurent|Luc|Lucas|Manon|Marc|Marie|Mathieu|Michel|Nathalie|"
    r"Nicolas|Olivier|Paul|Philippe|Pierre|Sophie|Thomas|Valérie|Victor"
)

_FIREWALL_ONLY_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "siret_ocr_labeled",
        re.compile(
            r"\bSIRET\s*(?:n[°o]\s*)?[:\-]?\s*"
            r"[0-9O]{3}[\s.\-]?[0-9O]{3}[\s.\-]?[0-9O]{3}[\s.\-]?[0-9O]{5}\b",
            re.IGNORECASE,
        ),
        TOKEN_SIRET,
    ),
    (
        "person_name_common",
        re.compile(
            rf"\b(?i:{_COMMON_FIRST_NAMES_RE})"
            r"(?:[-\s]+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ''\-]{2,}){1,3}\b"
        ),
        TOKEN_PERSONNE,
    ),
    (
        "person_uppercase_labeled",
        re.compile(
            r"(?i)\b(?:nom|pr[ée]nom|client|dirigeant|g[ée]rant|b[ée]n[ée]ficiaire|titulaire)"
            r"\s*[:\-]\s*[A-ZÀ-ÖØ-Ý]{2,}(?:[ \t]+[A-ZÀ-ÖØ-Ý]{2,}){1,3}\b"
        ),
        TOKEN_PERSONNE,
    ),
]

_PATTERNS_BY_NAME: dict[str, tuple[re.Pattern[str], str]] = {
    name: (pattern, token) for name, pattern, token in [*PATTERNS, *_FIREWALL_ONLY_PATTERNS]
}


def _firewall_patterns() -> list[tuple[str, re.Pattern[str], str]]:
    """Curated (entity_type, regex, token) list, ordered for safe sequential redaction."""
    out: list[tuple[str, re.Pattern[str], str]] = []
    for name, entity_type in _PATTERN_NAME_TO_TYPE:
        spec = _PATTERNS_BY_NAME.get(name)
        if spec is None:
            continue
        pattern, token = spec
        out.append((entity_type, pattern, token))
    return out


_FIREWALL_PATTERNS = _firewall_patterns()


def _skip_firewall_match(entity_type: str, value: str) -> bool:
    if entity_type != "PERSONNE":
        return False
    if is_false_positive(value):
        return True
    return bool(
        re.match(
            r"(?i)\b(?:d[ée]nomination|nom\s+complet|naissance|total|r[ée]sultat|bilan|actif|passif)\b",
            value,
        )
    )


@dataclass
class FirewallFinding:
    """A class of residual PII detected in inspected text. Holds no raw value."""

    entity_type: str
    severity: str
    count: int
    token: str


@dataclass
class FirewallScan:
    findings: list[FirewallFinding] = field(default_factory=list)
    risk_score: float = 0.0
    risk_level: str = "low"
    verdict: str = ALLOW
    sanitized_text: str = ""
    direction: str = "text"

    @property
    def blocked(self) -> bool:
        return self.verdict == BLOCK

    @property
    def redacted(self) -> bool:
        return self.verdict == REDACT


def _risk_level(findings: list[FirewallFinding]) -> str:
    severities = {f.severity for f in findings}
    if "critical" in severities:
        return "critical"
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def _risk_score(findings: list[FirewallFinding]) -> float:
    score = sum(_SEVERITY_WEIGHT.get(f.severity, 0.0) * f.count for f in findings)
    return round(min(100.0, score), 1)


def decide_verdict(
    findings: list[FirewallFinding],
    risk_level: str,
    *,
    sensitive_mode: bool,
) -> str:
    """Context-aware verdict.

    - no residual PII            -> allow
    - critical risk              -> block (every mode)
    - SENSITIVE_CLIENT_MODE      -> block
    - otherwise (normal / demo)  -> redact + log
    """
    if not findings:
        return ALLOW
    if risk_level == "critical":
        return BLOCK
    if sensitive_mode:
        return BLOCK
    return REDACT


def scan_text(
    text: str,
    *,
    sensitive_mode: bool = False,
    direction: str = "text",
) -> FirewallScan:
    """Inspect text for residual direct identifiers and return a firewall verdict.

    The returned ``sanitized_text`` always has every detected identifier replaced
    by its anonymization token, regardless of verdict, so callers may forward the
    sanitized version on a ``redact`` verdict.
    """
    working = text or ""
    counts: dict[str, int] = {}
    tokens: dict[str, str] = {}

    for entity_type, pattern, token in _FIREWALL_PATTERNS:
        def replace(
            match: re.Match[str],
            current_entity_type: str = entity_type,
            current_token: str = token,
        ) -> str:
            value = match.group(0)
            if _skip_firewall_match(current_entity_type, value):
                return value
            counts[current_entity_type] = counts.get(current_entity_type, 0) + 1
            tokens.setdefault(current_entity_type, current_token)
            return current_token

        working = pattern.sub(replace, working)

    findings = [
        FirewallFinding(
            entity_type=entity_type,
            severity=_SEVERITY.get(entity_type, "medium"),
            count=count,
            token=tokens[entity_type],
        )
        for entity_type, count in counts.items()
    ]
    # Stable, severity-first ordering for readable summaries.
    severity_rank = {"critical": 0, "high": 1, "medium": 2}
    findings.sort(key=lambda f: (severity_rank.get(f.severity, 9), f.entity_type))

    risk_level = _risk_level(findings)
    verdict = decide_verdict(findings, risk_level, sensitive_mode=sensitive_mode)

    return FirewallScan(
        findings=findings,
        risk_score=_risk_score(findings),
        risk_level=risk_level,
        verdict=verdict,
        sanitized_text=working,
        direction=direction,
    )


def firewall_summary(scan: FirewallScan) -> dict[str, object]:
    """Public, leak-safe summary for API responses and structured logs."""
    return {
        "direction": scan.direction,
        "verdict": scan.verdict,
        "risk_level": scan.risk_level,
        "risk_score": scan.risk_score,
        "findings": [
            {"entity_type": f.entity_type, "severity": f.severity, "count": f.count}
            for f in scan.findings
        ],
    }
