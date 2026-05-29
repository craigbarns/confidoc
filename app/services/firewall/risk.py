"""AI Firewall — residual-PII detection, risk scoring, verdict and redaction.

This module is deterministic and dependency-light. It reuses the existing
anonymization regex patterns (single source of truth) instead of duplicating
them, so the firewall stays in sync with the anonymization engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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
    ("siret", "SIRET"),
    ("phone_fr", "TELEPHONE"),
    ("phone_intl", "TELEPHONE"),
    ("email", "EMAIL"),
    ("siren", "SIREN"),
    ("person_title", "PERSONNE"),
    ("address_line", "ADRESSE"),
    ("postal_city", "VILLE"),
]

_PATTERNS_BY_NAME: dict[str, tuple[re.Pattern[str], str]] = {
    name: (pattern, token) for name, pattern, token in PATTERNS
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
        working, n = pattern.subn(token, working)
        if n:
            counts[entity_type] = counts.get(entity_type, 0) + n
            tokens.setdefault(entity_type, token)

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
