"""AI Firewall — inbound response guard.

Inspects the text returned by an LLM before it reaches the user. Catches direct
identifiers the model may have surfaced or hallucinated, blocking the leak or
masking it depending on the active mode.
"""

from __future__ import annotations

from app.services.firewall.risk import FirewallScan, scan_text


def inspect_response(text: str, *, sensitive_mode: bool = False) -> FirewallScan:
    """Scan an inbound AI response and return a context-aware firewall verdict."""
    return scan_text(text, sensitive_mode=sensitive_mode, direction="response")
