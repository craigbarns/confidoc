"""Tests for webhook retry with exponential backoff."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.webhook_notify import (
    notify_document_validated,
    MAX_RETRIES,
    BACKOFF_BASE_SECONDS,
)


@pytest.mark.asyncio
async def test_webhook_success_first_attempt():
    """Webhook should succeed on first attempt and not retry."""
    with patch("app.services.webhook_notify.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notify_document_validated(
            document_id="test-123",
            url="https://example.com/webhook",
            secret="",
        )
        assert mock_client.post.call_count == 1


@pytest.mark.asyncio
async def test_webhook_retries_on_500():
    """Webhook should retry on 5xx errors with backoff."""
    call_count = 0

    with patch("app.services.webhook_notify.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.webhook_notify.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500
        mock_response_500.text = "Internal Server Error"

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200

        mock_client = AsyncMock()
        # Fail twice, then succeed
        mock_client.post.side_effect = [mock_response_500, mock_response_500, mock_response_200]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notify_document_validated(
            document_id="test-456",
            url="https://example.com/webhook",
        )
        assert mock_client.post.call_count == 3
        # Should have slept twice (backoff between retries)
        assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_webhook_no_retry_on_4xx():
    """Webhook should NOT retry on 4xx client errors."""
    with patch("app.services.webhook_notify.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.webhook_notify.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notify_document_validated(
            document_id="test-789",
            url="https://example.com/webhook",
        )
        assert mock_client.post.call_count == 1
        assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_webhook_retries_on_network_error():
    """Webhook should retry on network exceptions."""
    with patch("app.services.webhook_notify.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.webhook_notify.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200

        mock_client = AsyncMock()
        mock_client.post.side_effect = [
            ConnectionError("Connection refused"),
            mock_response_ok,
        ]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notify_document_validated(
            document_id="test-conn",
            url="https://example.com/webhook",
        )
        assert mock_client.post.call_count == 2
        assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_webhook_exhausts_retries():
    """Webhook should give up after MAX_RETRIES attempts."""
    with patch("app.services.webhook_notify.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.webhook_notify.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = AsyncMock()
        mock_client.post.side_effect = ConnectionError("Always fails")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notify_document_validated(
            document_id="test-exhaust",
            url="https://example.com/webhook",
        )
        assert mock_client.post.call_count == MAX_RETRIES
        assert mock_sleep.call_count == MAX_RETRIES - 1


@pytest.mark.asyncio
async def test_webhook_hmac_signature():
    """Webhook should include HMAC signature when secret is provided."""
    with patch("app.services.webhook_notify.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notify_document_validated(
            document_id="test-sig",
            url="https://example.com/webhook",
            secret="my-secret",
        )

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs[1]["headers"]
        assert "X-ConfiDoc-Signature" in headers
        assert headers["X-ConfiDoc-Signature"].startswith("sha256=")


@pytest.mark.asyncio
async def test_webhook_exponential_backoff_timing():
    """Backoff delays should follow exponential pattern: 2s, 4s, 8s."""
    with patch("app.services.webhook_notify.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.webhook_notify.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = AsyncMock()
        mock_client.post.side_effect = ConnectionError("Always fails")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await notify_document_validated(
            document_id="test-backoff",
            url="https://example.com/webhook",
        )

        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        expected = [BACKOFF_BASE_SECONDS * (2 ** i) for i in range(MAX_RETRIES - 1)]
        assert sleep_calls == expected


def test_retry_config():
    """Retry configuration should have sensible defaults."""
    assert MAX_RETRIES == 4
    assert BACKOFF_BASE_SECONDS == 2
