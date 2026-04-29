"""Tests for optional RAG embedding behavior."""

from app.config import Settings
from app.services import rag_service


def test_get_embed_model_skips_loading_when_disabled(monkeypatch):
    """Disabled RAG embeddings should not import or download the model."""
    monkeypatch.setattr(
        rag_service,
        "get_settings",
        lambda: Settings(RAG_EMBEDDINGS_ENABLED=False),
    )
    monkeypatch.setattr(rag_service, "_EMBED_MODEL", None)
    monkeypatch.setattr(rag_service, "_EMBED_MODEL_NAME", None)

    assert rag_service._get_embed_model() is None
