"""Notifications HTTP optionnelles (validation document, etc.)."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


async def notify_document_validated(*, document_id: str, url: str, secret: str = "") -> None:
    """POST JSON ``{event, document_id}`` — signature HMAC-SHA256 si ``secret`` est défini."""
    payload = {"event": "document_validated", "document_id": document_id}
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
    if secret.strip():
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-ConfiDoc-Signature"] = f"sha256={sig}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url.strip(), content=body, headers=headers)
            if r.status_code >= 400:
                logger.warning(
                    "webhook_validate_http_error",
                    url=url,
                    status_code=r.status_code,
                    body_preview=r.text[:200],
                )
    except Exception as exc:
        logger.warning("webhook_validate_failed", url=url, error=str(exc))
