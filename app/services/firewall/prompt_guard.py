"""AI Firewall — outbound prompt guard.

Inspects the text about to be sent to an LLM. Catches residual direct
identifiers the anonymization pipeline may have missed before they ever leave
the perimeter.
"""

from __future__ import annotations

from app.services.firewall.risk import FirewallScan, scan_text


def inspect_prompt(text: str, *, sensitive_mode: bool = False) -> FirewallScan:
    """Scan an outbound prompt and return a context-aware firewall verdict."""
    return scan_text(text, sensitive_mode=sensitive_mode, direction="prompt")
