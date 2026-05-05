"""Tests for sensitive client mode external-AI guardrails."""

from __future__ import annotations

import pytest

from app.config import Settings


def test_select_llm_provider_disables_external_ai(monkeypatch):
    from app.api.v1 import ai

    settings = Settings(
        SENSITIVE_CLIENT_MODE=True,
        MISTRAL_ENABLED=True,
        MISTRAL_API_KEY="test-key",
        OLLAMA_ENABLED=False,
    )
    monkeypatch.setattr(ai, "get_settings", lambda: settings)

    assert ai._select_llm_provider("auto") == "disabled"
    assert ai._select_llm_provider("mistral") == "disabled"


def test_select_llm_provider_allows_local_ollama_in_sensitive_mode(monkeypatch):
    from app.api.v1 import ai

    settings = Settings(
        SENSITIVE_CLIENT_MODE=True,
        MISTRAL_ENABLED=True,
        MISTRAL_API_KEY="test-key",
        OLLAMA_ENABLED=True,
    )
    monkeypatch.setattr(ai, "get_settings", lambda: settings)

    assert ai._select_llm_provider("ollama") == "ollama"
    assert ai._select_llm_provider("auto") == "disabled"


@pytest.mark.asyncio
async def test_llm_extraction_uses_sensitive_mode_fallback(monkeypatch):
    from app.services import llm_extraction_service

    settings = Settings(
        SENSITIVE_CLIENT_MODE=True,
        MISTRAL_ENABLED=True,
        MISTRAL_API_KEY="test-key",
    )
    monkeypatch.setattr(llm_extraction_service, "get_settings", lambda: settings)

    result = await llm_extraction_service.extract_with_llm(
        "Client [PERSONNE_1] - total actif 1000"
    )

    assert result["source"] == "disabled:sensitive_client_mode"
    assert result["montants_cles"] == []
