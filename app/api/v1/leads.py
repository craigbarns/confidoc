"""ConfiDoc — Public beta lead capture endpoints."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.config import get_settings
from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.models.audit_log import AuditLog
from app.models.beta_lead import BetaLead
from app.schemas.lead import BetaLeadCreate, BetaLeadResponse
from app.services.email_service import send_beta_lead_notification

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()

_BETA_LEAD_RATE_WINDOW = 3600
_BETA_LEAD_RATE_MAX = 6
_beta_lead_attempts_fallback: dict[str, list[float]] = {}


async def _check_beta_lead_rate_limit(key: str) -> None:
    """Limit public lead submissions without making Redis mandatory."""
    redis_key = f"confidoc:beta_lead_rl:{key}"
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
        async with r:
            pipe = r.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, _BETA_LEAD_RATE_WINDOW)
            results = await pipe.execute()
            count = int(results[0])
        if count > _BETA_LEAD_RATE_MAX:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Trop de demandes beta. Réessayez plus tard.",
            )
        return
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("beta_lead_rate_limit_redis_unavailable", error=str(exc))

    now = time.time()
    attempts = _beta_lead_attempts_fallback.get(key, [])
    attempts = [t for t in attempts if now - t < _BETA_LEAD_RATE_WINDOW]
    if len(attempts) >= _BETA_LEAD_RATE_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de demandes beta. Réessayez plus tard.",
        )
    attempts.append(now)
    _beta_lead_attempts_fallback[key] = attempts


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()[:16]


async def _persist_beta_lead(payload: BetaLeadCreate, request: Request) -> bool:
    """Persist or update a beta lead. Returns False when storage is unavailable."""
    data = payload.model_dump()
    email = str(payload.email).lower()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:300]

    try:
        async with async_session_factory() as db:
            result = await db.execute(select(BetaLead).where(BetaLead.email == email))
            lead = result.scalar_one_or_none()
            if lead is None:
                lead = BetaLead(email=email, **{k: v for k, v in data.items() if k != "email"})
                db.add(lead)
                action = "beta_lead:create"
            else:
                for key, value in data.items():
                    if key != "email":
                        setattr(lead, key, value)
                action = "beta_lead:update"

            lead.metadata_json = {
                "ip_address": client_ip,
                "user_agent": user_agent,
                "email_hash": _email_hash(email),
            }
            await db.flush()

            db.add(
                AuditLog(
                    user_id=None,
                    org_id=None,
                    action=action,
                    resource_type="beta_lead",
                    resource_id=str(lead.id),
                    method="POST",
                    path="/api/v1/leads/beta",
                    status_code=201,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    details={
                        "email_hash": _email_hash(email),
                        "source": payload.source,
                        "team_size": payload.team_size,
                        "document_volume": payload.document_volume,
                    },
                )
            )
            await db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "beta_lead_persist_failed",
            error=str(exc),
            email_hash=_email_hash(email),
            source=payload.source,
        )
        return False


@router.post(
    "/beta",
    response_model=BetaLeadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capturer une demande d'accès beta",
)
async def create_beta_lead(payload: BetaLeadCreate, request: Request) -> dict[str, Any]:
    """Capture a public beta access request without authentication."""
    client_ip = request.client.host if request.client else "unknown"
    await _check_beta_lead_rate_limit(client_ip)

    stored = await _persist_beta_lead(payload, request)
    notification_sent = await send_beta_lead_notification(payload.model_dump())

    logger.info(
        "beta_lead_received",
        stored=stored,
        notification_sent=notification_sent,
        source=payload.source,
        email_hash=_email_hash(str(payload.email)),
    )

    return {
        "status": "received",
        "message": "Demande reçue. Nous revenons vers vous rapidement.",
    }
