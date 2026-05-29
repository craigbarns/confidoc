"""ConfiDoc Backend — AI Firewall governance endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser
from app.config import get_settings
from app.services.firewall.stats import get_stats

router = APIRouter()


@router.get(
    "/stats",
    response_class=JSONResponse,
    status_code=status.HTTP_200_OK,
    summary="Compteurs de gouvernance de l'AI Firewall",
)
async def firewall_stats(current_user: CurrentUser) -> JSONResponse:
    """Expose the AI Firewall governance counters for the DPO/RSSI dashboard.

    Counters are best-effort (Redis-backed): prompts/responses scanned,
    redactions, blocks and critical risks intercepted. No raw PII is exposed.
    """
    settings = get_settings()
    counters = await get_stats()
    return JSONResponse(
        {
            "firewall": {
                "enabled": bool(getattr(settings, "AI_FIREWALL_ENABLED", True)),
                "mode": (
                    "strict" if getattr(settings, "SENSITIVE_CLIENT_MODE", False) else "redact"
                ),
                "policy": (
                    "Tous les échanges IA sont inspectés par l'AI Firewall "
                    "(prompt sortant et réponse entrante)."
                ),
            },
            "counters": counters,
        }
    )
