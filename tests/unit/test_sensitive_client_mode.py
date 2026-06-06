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

    result = await llm_extraction_service.extract_with_llm("Client [PERSONNE_1] - total actif 1000")

    assert result["source"] == "disabled:sensitive_client_mode"
    assert result["montants_cles"] == []


@pytest.mark.asyncio
async def test_llm_anonymization_raw_text_is_disabled_by_default(monkeypatch):
    from app.services import llm_anonymization_service

    settings = Settings(
        SENSITIVE_CLIENT_MODE=False,
        MISTRAL_ENABLED=True,
        MISTRAL_API_KEY="test-key",
        LLM_RAW_ANONYMIZATION_ENABLED=False,
    )
    monkeypatch.setattr(llm_anonymization_service, "get_settings", lambda: settings)
    monkeypatch.setattr(llm_anonymization_service, "_fallback_anonymize", lambda text: "[PERSONNE]")

    async def fail_if_called(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("raw text must not be sent to Mistral without explicit opt-in")

    monkeypatch.setattr(llm_anonymization_service, "_chat_completion", fail_if_called)

    result = await llm_anonymization_service.anonymize_with_llm("Jean Dupont")

    assert result["anonymized_text"] == "[PERSONNE]"
    assert result["method"] == "fallback:regex_raw_llm_disabled"


@pytest.mark.asyncio
async def test_llm_anonymization_requires_explicit_raw_text_opt_in(monkeypatch):
    from app.services import llm_anonymization_service

    settings = Settings(
        SENSITIVE_CLIENT_MODE=False,
        MISTRAL_ENABLED=True,
        MISTRAL_API_KEY="test-key",
        LLM_RAW_ANONYMIZATION_ENABLED=True,
    )
    monkeypatch.setattr(llm_anonymization_service, "get_settings", lambda: settings)

    async def fake_chat_completion(prompt: str, temperature: float = 0.1) -> str:
        assert "Jean Dupont" in prompt
        assert temperature == 0.1
        return (
            '{"texte_anonymise":"[PERSONNE]","entites_detectees":['
            '{"type":"PERSONNE","valeur_originale":"Jean Dupont",'
            '"position_debut":0,"position_fin":11,"token":"[PERSONNE]"}],'
            '"confiance":"high","nb_remplacements":1}'
        )

    monkeypatch.setattr(llm_anonymization_service, "_chat_completion", fake_chat_completion)

    result = await llm_anonymization_service.anonymize_with_llm("Jean Dupont")

    assert result["anonymized_text"] == "[PERSONNE]"
    assert result["method"] == "llm:mistral-large"
    assert result["count"] == 1
