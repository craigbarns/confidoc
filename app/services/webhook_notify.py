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


async def _post_json_with_retry(
    *,
    payload: dict,
    url: str,
    secret: str = "",
    event: str | None = None,
) -> tuple[bool, int | None, str | None, int, str | None]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
    if event:
        headers["X-ConfiDoc-Event"] = event
    if secret.strip():
        sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-ConfiDoc-Signature"] = f"sha256={sig}"

    last_error: str | None = None
    last_status: int | None = None
    last_response_preview: str | None = None
    attempts = 0
    for attempt in range(1, MAX_RETRIES + 1):
        attempts = attempt
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(url.strip(), content=body, headers=headers)
                response_text = str(getattr(r, "text", "") or "")
                last_status = r.status_code
                last_response_preview = response_text[:500]
                if r.status_code < 400:
                    logger.info(
                        "webhook_delivered",
                        url=url,
                        attempt=attempt,
                        status_code=r.status_code,
                        webhook_event=event,
                    )
                    return True, r.status_code, None, attempts, last_response_preview
                last_error = f"HTTP {r.status_code}: {response_text[:200]}"
                logger.warning(
                    "webhook_http_error",
                    url=url,
                    status_code=r.status_code,
                    attempt=attempt,
                    body_preview=response_text[:200],
                    webhook_event=event,
                )
                if 400 <= r.status_code < 500:
                    logger.warning(
                        "webhook_client_error_no_retry",
                        url=url,
                        status_code=r.status_code,
                        webhook_event=event,
                    )
                    return False, r.status_code, last_error, attempts, last_response_preview
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "webhook_attempt_failed",
                url=url,
                attempt=attempt,
                error=str(exc),
                webhook_event=event,
            )

        if attempt < MAX_RETRIES:
            wait = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            logger.info("webhook_retry_wait", url=url, wait_seconds=wait, next_attempt=attempt + 1)
            await asyncio.sleep(wait)

    logger.error(
        "webhook_exhausted_retries",
        url=url,
        max_retries=MAX_RETRIES,
        last_error=last_error,
        webhook_event=event,
    )
    return False, last_status, last_error, attempts, last_response_preview


async def notify_json_webhook(
    *,
    event: str,
    payload: dict,
    url: str,
    secret: str = "",
) -> tuple[bool, int | None, str | None, int, str | None]:
    """POST a JSON webhook payload with retry and HMAC signature."""
    return await _post_json_with_retry(payload=payload, url=url, secret=secret, event=event)


async def notify_document_validated(*, document_id: str, url: str, secret: str = "") -> None:
    """POST JSON ``{event, document_id}`` avec retry exponentiel et signature HMAC-SHA256."""
    payload = {"event": "document_validated", "document_id": document_id}
    await _post_json_with_retry(
        payload=payload,
        url=url,
        secret=secret,
        event="document_validated",
    )
