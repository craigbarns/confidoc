"""ConfiDoc AI Firewall.

Defense-in-depth layer that inspects the *actual text* exchanged with any LLM —
the outbound prompt and the inbound response — on top of the metadata-level
Privacy Gate. It detects residual direct identifiers (PII the anonymization
pipeline may have missed), scores the re-identification risk before/after the
AI call, and applies a context-aware verdict:

- normal / demo mode  -> redact residual PII and log the incident (fluid demo)
- SENSITIVE_CLIENT_MODE -> block the call outright
- critical risk        -> block in every mode

No raw PII value ever leaves this package: findings expose entity types and
counts only, never the matched string.
"""

from app.services.firewall.prompt_guard import inspect_prompt
from app.services.firewall.response_guard import inspect_response
from app.services.firewall.risk import (
    ALLOW,
    BLOCK,
    REDACT,
    FirewallFinding,
    FirewallScan,
    firewall_summary,
    scan_text,
)

__all__ = [
    "ALLOW",
    "BLOCK",
    "REDACT",
    "FirewallFinding",
    "FirewallScan",
    "firewall_summary",
    "inspect_prompt",
    "inspect_response",
    "scan_text",
]
