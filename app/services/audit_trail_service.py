"""Audit trail helpers for RGPD traceability.

The audit log must be useful for compliance without becoming a second copy of
sensitive documents. This module centralizes safe metadata handling and keeps
raw text, mappings, secrets, and excerpts out of ``audit_logs.details``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import INSECURE_SECRET_PLACEHOLDER, get_settings
from app.models.audit_log import AuditLog

_SENSITIVE_DETAIL_KEY_PARTS = (
    "content",
    "excerpt",
    "mapping",
    "password",
    "raw",
    "secret",
    "snippet",
    "text",
    "token",
    "value",
)
_MAX_DETAIL_STRING_CHARS = 240
_MAX_DETAIL_LIST_ITEMS = 25
_MAX_DETAIL_DEPTH = 4


def _coerce_uuid(value: object | None) -> uuid.UUID | None:
    """Return a UUID object or ``None`` for invalid/missing values."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _hash_value(value: object) -> dict[str, object]:
    raw = str(value)
    return {
        "redacted": True,
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "length": len(raw),
    }


def _sanitize_value(key: str, value: object, *, depth: int) -> object:
    key_lower = key.lower()
    if any(part in key_lower for part in _SENSITIVE_DETAIL_KEY_PARTS):
        return _hash_value(value)

    if depth >= _MAX_DETAIL_DEPTH:
        return _hash_value(value)

    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, uuid.UUID):
        return str(value)

    if isinstance(value, str):
        if len(value) > _MAX_DETAIL_STRING_CHARS:
            return {
                "truncated": value[:_MAX_DETAIL_STRING_CHARS],
                "length": len(value),
            }
        return value

    if isinstance(value, dict):
        return {str(k)[:80]: _sanitize_value(str(k), v, depth=depth + 1) for k, v in value.items()}

    if isinstance(value, list | tuple | set):
        return [
            _sanitize_value(key, item, depth=depth + 1)
            for item in list(value)[:_MAX_DETAIL_LIST_ITEMS]
        ]

    return str(value)[:_MAX_DETAIL_STRING_CHARS]


def sanitize_audit_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a JSON-safe, PII-minimized audit details dict."""
    if not details:
        return None
    sanitized = {
        str(key)[:80]: _sanitize_value(str(key), value, depth=0) for key, value in details.items()
    }
    return sanitized or None


def build_audit_event_hash(
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    method: str,
    path: str,
    status_code: int,
    user_id: object | None,
    org_id: object | None,
    details: dict[str, Any] | None,
) -> str:
    """Build a stable HMAC over the non-sensitive event payload."""
    settings = get_settings()
    secret = (settings.SECRET_KEY or settings.JWT_SECRET_KEY or INSECURE_SECRET_PLACEHOLDER).encode(
        "utf-8"
    )
    payload = {
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "user_id": str(user_id) if user_id else None,
        "org_id": str(org_id) if org_id else None,
        "details": details or {},
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()


async def record_audit_event(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str | uuid.UUID | None = None,
    user_id: object | None = None,
    org_id: object | None = None,
    method: str = "SYSTEM",
    path: str = "system",
    status_code: int = 200,
    ip_address: str | None = None,
    user_agent: str | None = None,
    actor_type: str = "system",
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Add one audit event to the current transaction.

    The caller decides when to commit. This keeps pipeline step audit rows
    atomic with their corresponding document status/version changes.
    """
    safe_details = sanitize_audit_details(details)
    resource_id_str = str(resource_id) if resource_id is not None else None
    event_hash = build_audit_event_hash(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id_str,
        method=method,
        path=path,
        status_code=status_code,
        user_id=user_id,
        org_id=org_id,
        details=safe_details,
    )

    entry = AuditLog(
        user_id=_coerce_uuid(user_id),
        org_id=_coerce_uuid(org_id),
        actor_type=actor_type[:20],
        action=action[:80],
        resource_type=resource_type[:40],
        resource_id=resource_id_str[:64] if resource_id_str else None,
        method=method[:10],
        path=path[:500],
        status_code=status_code,
        ip_address=ip_address[:45] if ip_address else None,
        user_agent=user_agent[:500] if user_agent else None,
        request_id=request_id[:64] if request_id else None,
        event_hash=event_hash,
        details=safe_details,
    )
    db.add(entry)
    await db.flush()
    return entry


async def record_document_audit_event(
    db: AsyncSession,
    *,
    document: object,
    action: str,
    status_code: int = 200,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Convenience wrapper for system events attached to a document."""
    return await record_audit_event(
        db,
        action=action,
        resource_type="document",
        resource_id=getattr(document, "id", None),
        user_id=getattr(document, "uploaded_by_user_id", None),
        org_id=getattr(document, "org_id", None),
        method="SYSTEM",
        path=f"pipeline:{action}",
        status_code=status_code,
        actor_type="system",
        details=details,
    )
