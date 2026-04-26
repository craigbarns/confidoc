"""Services for API keys, idempotency and integration webhooks."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import http_400, http_401, http_403, http_409
from app.core.logging import get_logger
from app.core.security import generate_opaque_token, hash_token
from app.models.document import Document
from app.models.integration import ApiKey, IdempotencyRecord, WebhookDelivery, WebhookEndpoint
from app.models.membership import Membership
from app.models.user import User

logger = get_logger(__name__)

API_KEY_PREFIX = "confidoc_live_"
IDEMPOTENCY_TTL_HOURS = 24


def is_api_key_token(value: str | None) -> bool:
    return bool(value and value.strip().startswith(API_KEY_PREFIX))


def generate_api_key_value() -> str:
    return f"{API_KEY_PREFIX}{generate_opaque_token(32)}"


def api_key_prefix(value: str) -> str:
    return value[:24]


async def authenticate_api_key(db: AsyncSession, raw_key: str) -> tuple[User, ApiKey, Membership]:
    """Authenticate a raw API key and return its user, key and active membership."""
    key_hash = hash_token(raw_key.strip())
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active.is_(True),
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise http_401("Cle API invalide")

    now = datetime.now(UTC)
    if api_key.revoked_at is not None:
        raise http_401("Cle API revoquee")
    if api_key.expires_at is not None and api_key.expires_at <= now:
        raise http_401("Cle API expiree")

    result = await db.execute(select(User).where(User.id == api_key.created_by_user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise http_403("Utilisateur API desactive")

    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.org_id == api_key.org_id,
            Membership.is_active.is_(True),
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise http_403("Cle API sans organisation active")

    api_key.last_used_at = now
    return user, api_key, membership


def build_request_hash(parts: dict[str, Any]) -> str:
    """Stable SHA-256 fingerprint for an idempotent write request."""
    body = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def normalize_idempotency_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if len(value) > 160:
        raise http_400("Idempotency-Key trop longue")
    return value


async def get_idempotency_replay(
    db: AsyncSession,
    *,
    user_id: UUID,
    route: str,
    idempotency_key: str | None,
    request_hash: str,
) -> IdempotencyRecord | None:
    key = normalize_idempotency_key(idempotency_key)
    if not key:
        return None

    result = await db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.created_by_user_id == user_id,
            IdempotencyRecord.route == route,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        return None
    if record.request_hash != request_hash:
        raise http_409(
            "Idempotency-Key deja utilisee avec une requete differente"
        )
    return record


async def store_idempotency_response(
    db: AsyncSession,
    *,
    user_id: UUID,
    org_id: UUID | None,
    route: str,
    idempotency_key: str | None,
    request_hash: str,
    response_body: dict,
    status_code: int,
    document_id: UUID | None = None,
) -> None:
    key = normalize_idempotency_key(idempotency_key)
    if not key:
        return
    expires_at = datetime.now(UTC) + timedelta(hours=IDEMPOTENCY_TTL_HOURS)
    db.add(
        IdempotencyRecord(
            org_id=org_id,
            created_by_user_id=user_id,
            document_id=document_id,
            route=route,
            idempotency_key=key,
            request_hash=request_hash,
            status_code=status_code,
            response_body=response_body,
            expires_at=expires_at,
        )
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("idempotency_store_failed", route=route, user_id=str(user_id))


def document_event_payload(
    *,
    document: Document,
    event: str,
    event_id: str,
) -> dict[str, Any]:
    settings = get_settings()
    base_url = settings.APP_BASE_URL.rstrip("/")
    client_name = document.tags[0] if document.tags else None
    status_value = (
        document.status.value if hasattr(document.status, "value") else str(document.status)
    )
    return {
        "event": event,
        "event_id": event_id,
        "created_at": datetime.now(UTC).isoformat(),
        "document": {
            "id": str(document.id),
            "status": status_value,
            "client_name": client_name,
            "original_filename": document.original_filename,
            "sha256": document.sha256,
            "size_bytes": document.size_bytes,
        },
        "links": {
            "status": f"{base_url}/api/v1/documents/{document.id}/status",
            "preview": f"{base_url}/api/v1/documents/{document.id}/preview",
            "structured": f"{base_url}/api/v1/documents/{document.id}/structured?include_text=true",
            "audit_report_pdf": f"{base_url}/api/v1/documents/{document.id}/audit-report-pdf",
        },
    }


async def dispatch_document_event(document_id: str, event: str) -> None:
    """Send configured organization webhooks for a document event."""
    from app.core.database import async_session_factory
    from app.services.webhook_notify import notify_json_webhook

    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.id == UUID(document_id)))
        document = result.scalar_one_or_none()
        if not document or not document.org_id:
            return

        result = await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.org_id == document.org_id,
                WebhookEndpoint.is_active.is_(True),
            )
        )
        endpoints = [
            endpoint
            for endpoint in result.scalars().all()
            if event in (endpoint.events or [])
        ]
        if not endpoints:
            return

        for endpoint in endpoints:
            event_id = generate_opaque_token(18)
            payload = document_event_payload(document=document, event=event, event_id=event_id)
            delivery = WebhookDelivery(
                org_id=document.org_id,
                endpoint_id=endpoint.id,
                document_id=document.id,
                event=event,
                event_id=event_id,
                payload=payload,
            )
            db.add(delivery)
            await db.commit()
            delivered, status_code, error, attempts, response_preview = await notify_json_webhook(
                event=event,
                payload=payload,
                url=endpoint.url,
                secret=endpoint.signing_secret,
            )
            delivery.status = "delivered" if delivered else "failed"
            delivery.status_code = status_code
            delivery.error = error
            delivery.attempts = attempts
            delivery.response_body_preview = response_preview
            now = datetime.now(UTC)
            if delivered:
                endpoint.last_success_at = now
                endpoint.failure_count = 0
            else:
                endpoint.last_failure_at = now
                endpoint.failure_count = (endpoint.failure_count or 0) + 1
            await db.commit()
