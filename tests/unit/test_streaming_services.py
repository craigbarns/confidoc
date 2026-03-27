"""Tests pour le fix du streaming LLM (bug "Load failed").

Vérifie que le générateur stream_mistral_response
ne lèvent jamais d'exception non attrapée — ils yielden toujours un message
d'erreur propre, même si l'API LLM retourne un code d'erreur ou une
exception réseau.
"""

import pytest
import httpx

from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────

async def collect_chunks(async_gen) -> list[str]:
    """Collecte tous les chunks d'un async generator dans une liste."""
    chunks = []
    async for chunk in async_gen:
        chunks.append(chunk)
    return chunks


# ── Tests stream_mistral_response ──────────────────────────────────────

class TestStreamMistralResponse:

    @pytest.mark.asyncio
    async def test_disabled_yields_message(self):
        """Si MISTRAL_ENABLED=False, le générateur yielde un message et s'arrête."""
        from app.services.mistral_service import stream_mistral_response

        with patch("app.services.mistral_service.get_settings") as mock_settings:
            s = MagicMock()
            s.MISTRAL_ENABLED = False
            s.MISTRAL_API_KEY = ""
            mock_settings.return_value = s

            chunks = await collect_chunks(stream_mistral_response("test"))
            assert len(chunks) == 1
            assert "non disponible" in chunks[0].lower() or "mistral" in chunks[0].lower()

    @pytest.mark.asyncio
    async def test_no_api_key_yields_message(self):
        """Sans clé API, le générateur yielde un message sans lever d'exception."""
        from app.services.mistral_service import stream_mistral_response

        with patch("app.services.mistral_service.get_settings") as mock_settings:
            s = MagicMock()
            s.MISTRAL_ENABLED = True
            s.MISTRAL_API_KEY = ""
            mock_settings.return_value = s

            chunks = await collect_chunks(stream_mistral_response("test"))
            assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_api_401_yields_error_not_raises(self):
        """Une réponse 401 de l'API ne doit PAS lever d'exception — yielde un message d'erreur."""
        from app.services.mistral_service import stream_mistral_response

        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.aread = AsyncMock(return_value=b'{"message": "Unauthorized"}')

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.mistral_service.get_settings") as mock_settings, \
             patch("app.services.mistral_service.httpx.AsyncClient", return_value=mock_client_ctx):
            s = MagicMock()
            s.MISTRAL_ENABLED = True
            s.MISTRAL_API_KEY = "test-key"
            s.MISTRAL_BASE_URL = "https://api.mistral.ai"
            s.MISTRAL_MODEL = "mistral-large-latest"
            s.MISTRAL_TIMEOUT_SECONDS = 60
            mock_settings.return_value = s

            # Ne doit PAS lever d'exception
            chunks = await collect_chunks(stream_mistral_response("test question"))

        assert len(chunks) == 1
        assert "401" in chunks[0] or "erreur" in chunks[0].lower()

    @pytest.mark.asyncio
    async def test_timeout_yields_error_not_raises(self):
        """Un timeout réseau ne doit PAS lever d'exception — yielde un message."""
        from app.services.mistral_service import stream_mistral_response

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(
            side_effect=httpx.TimeoutException("Connection timed out")
        )
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.mistral_service.get_settings") as mock_settings, \
             patch("app.services.mistral_service.httpx.AsyncClient", return_value=mock_client_ctx):
            s = MagicMock()
            s.MISTRAL_ENABLED = True
            s.MISTRAL_API_KEY = "test-key"
            s.MISTRAL_BASE_URL = "https://api.mistral.ai"
            s.MISTRAL_MODEL = "mistral-large-latest"
            s.MISTRAL_TIMEOUT_SECONDS = 60
            mock_settings.return_value = s

            chunks = await collect_chunks(stream_mistral_response("test"))

        assert len(chunks) == 1
        assert "délai" in chunks[0].lower() or "timeout" in chunks[0].lower() or "erreur" in chunks[0].lower()

    @pytest.mark.asyncio
    async def test_network_error_yields_error_not_raises(self):
        """Une erreur réseau générique ne doit PAS lever d'exception."""
        from app.services.mistral_service import stream_mistral_response

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.mistral_service.get_settings") as mock_settings, \
             patch("app.services.mistral_service.httpx.AsyncClient", return_value=mock_client_ctx):
            s = MagicMock()
            s.MISTRAL_ENABLED = True
            s.MISTRAL_API_KEY = "test-key"
            s.MISTRAL_BASE_URL = "https://api.mistral.ai"
            s.MISTRAL_MODEL = "mistral-large-latest"
            s.MISTRAL_TIMEOUT_SECONDS = 60
            mock_settings.return_value = s

            chunks = await collect_chunks(stream_mistral_response("test"))

        assert len(chunks) == 1
        assert "erreur" in chunks[0].lower() or "mistral" in chunks[0].lower()

    @pytest.mark.asyncio
    async def test_successful_stream_yields_chunks(self):
        """Un stream 200 OK yielde les chunks de texte."""
        from app.services.mistral_service import stream_mistral_response

        sse_lines = [
            'data: {"choices": [{"delta": {"content": "Bonjour"}}]}',
            'data: {"choices": [{"delta": {"content": " monde"}}]}',
            "data: [DONE]",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        async def fake_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = fake_aiter_lines

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.mistral_service.get_settings") as mock_settings, \
             patch("app.services.mistral_service.httpx.AsyncClient", return_value=mock_client_ctx):
            s = MagicMock()
            s.MISTRAL_ENABLED = True
            s.MISTRAL_API_KEY = "test-key"
            s.MISTRAL_BASE_URL = "https://api.mistral.ai"
            s.MISTRAL_MODEL = "mistral-large-latest"
            s.MISTRAL_TIMEOUT_SECONDS = 60
            mock_settings.return_value = s

            chunks = await collect_chunks(stream_mistral_response("test"))

        assert chunks == ["Bonjour", " monde"]


