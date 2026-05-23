"""API helpers for enforcing the DPO Privacy Gate agent."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import http_400
from app.core.logging import get_logger
from app.models.document import Document
from app.services.agents.privacy_gate import evaluate_document_privacy_gate

logger = get_logger(__name__)


def privacy_gate_public_summary(result: dict) -> dict:
    return {
        "agent": result.get("agent"),
        "requested_action": result.get("requested_action"),
        "decision": result.get("decision"),
        "risk_level": result.get("risk_level"),
        "risk_score": result.get("risk_score"),
        "warnings": result.get("warnings") or [],
        "controls": result.get("allowed_controls") or [],
    }


def _blocked_detail(result: dict) -> str:
    decision = str(result.get("decision") or "block")
    reasons = result.get("reasons") or ["Décision DPO défavorable."]
    actions = result.get("required_actions") or []
    detail = f"Privacy Gate DPO: {decision}. " + " ".join(str(item) for item in reasons)
    if actions:
        detail += " Actions requises: " + " ".join(str(item) for item in actions)
    return detail


async def require_privacy_gate(
    db: AsyncSession,
    document: Document,
    requested_action: str,
    *,
    anonymized_text: str | None = None,
) -> dict:
    """Run the Privacy Gate and fail closed unless it explicitly allows the action."""
    try:
        result = await evaluate_document_privacy_gate(
            db,
            document,
            requested_action=requested_action,
            anonymized_text=anonymized_text,
        )
    except Exception as exc:
        logger.error(
            "privacy_gate_unavailable",
            document_id=str(getattr(document, "id", "")),
            requested_action=requested_action,
            error=str(exc),
        )
        raise http_400(
            "Privacy Gate DPO indisponible : action bloquée par sécurité."
        ) from exc

    if result.get("decision") != "allow":
        logger.warning(
            "privacy_gate_blocked_action",
            document_id=str(getattr(document, "id", "")),
            requested_action=requested_action,
            decision=result.get("decision"),
            reasons=result.get("reasons") or [],
        )
        raise http_400(_blocked_detail(result))
    return result
