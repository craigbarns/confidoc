"""ConfiDoc Backend — AI Firewall governance & demo endpoints.

These endpoints expose only non-sensitive aggregates (counters, event metadata
with entity types/counts — never raw PII) so the DPO/RSSI dashboard can be shown
publicly during investor/client demos, consistent with the public Trust Center.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.services.firewall import firewall_summary, inspect_prompt, inspect_response
from app.services.firewall.stats import get_recent_events, get_stats, record_scan

router = APIRouter()


def _firewall_state() -> dict:
    settings = get_settings()
    sensitive = bool(getattr(settings, "SENSITIVE_CLIENT_MODE", False))
    return {
        "enabled": bool(getattr(settings, "AI_FIREWALL_ENABLED", True)),
        "mode": "strict" if sensitive else "redact",
        "sensitive_client_mode": sensitive,
        "policy": (
            "Tous les échanges IA sont inspectés en temps réel "
            "(prompt sortant et réponse entrante)."
        ),
    }


@router.get(
    "/stats",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Compteurs et événements de l'AI Firewall",
)
async def firewall_stats() -> JSONResponse:
    """Expose the AI Firewall governance data for the DPO/RSSI dashboard.

    Best-effort (Redis-backed): prompts/responses scanned, redactions, blocks,
    critical risks, plus the most recent events. No raw PII is ever exposed.
    """
    counters = await get_stats()
    events = await get_recent_events(limit=20)
    return JSONResponse(
        {
            "firewall": _firewall_state(),
            "counters": counters,
            "recent_events": events,
        }
    )


# Synthetic, non-sensitive samples that tell the before/during/after-AI story.
_DEMO_SAMPLES: tuple[tuple[str, str, str], ...] = (
    (
        "prompt",
        "Avant l'IA — prompt envoyé",
        "Analyse le bilan anonymisé de [SOCIETE] pour l'exercice [DATE].",
    ),
    (
        "response",
        "Pendant l'IA — réponse contrôlée",
        "D'après le document, le contact comptable serait marie.martin@cabinet-exemple.fr.",
    ),
    (
        "response",
        "Tentative de fuite — interceptée",
        "Le RIB communiqué par le client est FR76 3000 4000 0500 0012 3456 789.",
    ),
)

_RESPONSE_BLOCKED_MESSAGE = (
    "🛡️ Réponse bloquée par l'AI Firewall avant restitution (donnée identifiante détectée)."
)


@router.post(
    "/demo",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Démo live de l'AI Firewall (séquence avant/pendant/après IA)",
)
async def firewall_demo() -> JSONResponse:
    """Run the firewall on synthetic samples to demonstrate live interception.

    No documents, no LLM, no auth. Records the scans so the dashboard counters
    and event feed update in real time during a client/investor demo.
    """
    settings = get_settings()
    sensitive = bool(getattr(settings, "SENSITIVE_CLIENT_MODE", False))

    steps: list[dict] = []
    for direction, label, text in _DEMO_SAMPLES:
        if direction == "prompt":
            scan = inspect_prompt(text, sensitive_mode=sensitive)
        else:
            scan = inspect_response(text, sensitive_mode=sensitive)
        await record_scan(scan)

        if scan.verdict == "block":
            output = _RESPONSE_BLOCKED_MESSAGE
        elif scan.verdict == "redact":
            output = scan.sanitized_text
        else:
            output = text

        steps.append(
            {
                "label": label,
                "direction": direction,
                "input": text,
                "output": output,
                "firewall": firewall_summary(scan),
            }
        )

    return JSONResponse(
        {
            "firewall": _firewall_state(),
            "steps": steps,
            "counters": await get_stats(),
            "recent_events": await get_recent_events(limit=20),
        }
    )
