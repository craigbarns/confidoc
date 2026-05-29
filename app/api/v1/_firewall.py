"""API helpers enforcing the AI Firewall around LLM calls.

Mirrors ``_privacy_gate.py``: the Privacy Gate decides *policy* on document
metadata, while the firewall inspects the *actual text* exchanged with the LLM.

- ``guard_outbound_prompt`` runs before the LLM call. On a ``block`` verdict it
  raises ``http_400`` (the call never leaves the perimeter). On ``redact`` it
  returns the sanitized text to send instead.
- ``guard_inbound_response`` runs after the LLM call. It never raises (the model
  already ran): on ``block`` it returns a safe placeholder so the leak is not
  restituted; on ``redact`` it returns the masked answer.

Logs carry entity types and counts only — never raw PII values.
"""

from __future__ import annotations

from app.config import get_settings
from app.core.exceptions import http_400
from app.core.logging import get_logger
from app.services.firewall import (
    BLOCK,
    REDACT,
    firewall_summary,
    inspect_prompt,
    inspect_response,
)
from app.services.firewall.stats import record_scan

logger = get_logger("ai_firewall")

_RESPONSE_BLOCKED_MESSAGE = (
    "🛡️ AI Firewall : la réponse générée contenait des données potentiellement "
    "identifiantes et a été bloquée avant restitution. Renforcez l'anonymisation "
    "du document puis relancez l'analyse."
)


def firewall_active() -> bool:
    return bool(getattr(get_settings(), "AI_FIREWALL_ENABLED", True))


def _sensitive_mode() -> bool:
    return bool(getattr(get_settings(), "SENSITIVE_CLIENT_MODE", False))


async def guard_outbound_prompt(text: str) -> tuple[str, dict | None]:
    """Inspect an outbound prompt. Returns (text_to_send, summary|None).

    Raises ``http_400`` when the firewall blocks the call.
    """
    if not firewall_active():
        return text, None

    scan = inspect_prompt(text, sensitive_mode=_sensitive_mode())
    await record_scan(scan)
    summary = firewall_summary(scan)

    if scan.verdict == BLOCK:
        logger.warning(
            "firewall_prompt_blocked",
            risk_level=scan.risk_level,
            risk_score=scan.risk_score,
            findings=summary["findings"],
        )
        raise http_400(
            "AI Firewall : données identifiantes résiduelles détectées dans la "
            "requête (mode client sensible ou risque critique) — appel IA bloqué."
        )

    if scan.verdict == REDACT:
        logger.info(
            "firewall_prompt_redacted",
            risk_level=scan.risk_level,
            findings=summary["findings"],
        )
        return scan.sanitized_text, summary

    return text, summary


async def guard_inbound_response(text: str) -> tuple[str, dict | None]:
    """Inspect an inbound AI response. Returns (safe_text, summary|None).

    Never raises: the model already ran. On a block verdict, a safe placeholder
    replaces the leaking answer.
    """
    if not firewall_active():
        return text, None

    scan = inspect_response(text, sensitive_mode=_sensitive_mode())
    await record_scan(scan)
    summary = firewall_summary(scan)

    if scan.verdict == BLOCK:
        logger.warning(
            "firewall_response_blocked",
            risk_level=scan.risk_level,
            risk_score=scan.risk_score,
            findings=summary["findings"],
        )
        return _RESPONSE_BLOCKED_MESSAGE, summary

    if scan.verdict == REDACT:
        logger.info(
            "firewall_response_redacted",
            risk_level=scan.risk_level,
            findings=summary["findings"],
        )
        return scan.sanitized_text, summary

    return text, summary
