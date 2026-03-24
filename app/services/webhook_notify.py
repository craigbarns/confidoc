"""Notifications HTTP optionnelles (validation document, etc.) avec retry exponentiel."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Retry configuration
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 2  # 2s, 4s, 8s, 16s


async def notify_document_validated(*, document_id: str, url: str, secret: str = "") -> None:
    """POST JSON ``{event, document_id}`` avec retry exponentiel et signature HMAC-SHA256."""
    payload = {"event": "document_validated", "document_id": document_id}
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
    if secret.strip():
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-ConfiDoc-Signature"] = f"sha256={sig}"

    last_error: str = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url.strip(), content=body, headers=headers)
                if r.status_code < 400:
                    logger.info(
                        "webhook_delivered",
                        url=url,
                        document_id=document_id,
                        attempt=attempt,
                        status_code=r.status_code,
                    )
                    return  # Success
                last_error = f"HTTP {r.status_code}: {r.text[:200]}"
                logger.warning(
                    "webhook_http_error",
                    url=url,
                    status_code=r.status_code,
                    attempt=attempt,
                    body_preview=r.text[:200],
                )
                # Don't retry on 4xx (client errors) — only retry on 5xx
                if 400 <= r.status_code < 500:
                    logger.warning(
                        "webhook_client_error_no_retry",
                        url=url,
                        status_code=r.status_code,
                    )
                    return
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "webhook_attempt_failed",
                url=url,
                attempt=attempt,
                error=str(exc),
            )

        # Exponential backoff before next retry
        if attempt < MAX_RETRIES:
            wait = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            logger.info("webhook_retry_wait", url=url, wait_seconds=wait, next_attempt=attempt + 1)
            await asyncio.sleep(wait)

    logger.error(
        "webhook_exhausted_retries",
        url=url,
        document_id=document_id,
        max_retries=MAX_RETRIES,
        last_error=last_error,
    )
