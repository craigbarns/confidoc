"""API tests for safe document-question streaming."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType


class _FakeResult:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeDb:
    def __init__(self, document: Document, version: DocumentVersion) -> None:
        self.document = document
        self.version = version

    async def execute(self, stmt: Any) -> _FakeResult:
        stmt_str = str(stmt).lower()
        if "from documents" in stmt_str:
            return _FakeResult(self.document)
        if "from document_versions" in stmt_str:
            return _FakeResult(self.version)
        return _FakeResult(None)


@pytest.fixture
def _ai_stream_setup():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    user = type(
        "User",
        (),
        {
            "id": user_id,
            "org_id": org_id,
            "is_active": True,
            "email": "qa@confidoc.test",
        },
    )()

    doc = Document(
        id=doc_id,
        org_id=org_id,
        uploaded_by_user_id=user_id,
        original_filename="liasse.pdf",
        content_type="application/pdf",
        extension="pdf",
        size_bytes=1024,
        sha256="abc" * 20,
        storage_backend="database",
        storage_key=f"uploads/{doc_id}.pdf",
        status=DocumentStatus.READY,
    )

    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc_id,
        version_type=DocumentVersionType.FINAL_ANONYMIZED,
        content_text="Document masqué avec [SOCIETE_1] et [MONTANT_1].",
    )

    fake_db = _FakeDb(doc, version)

    async def _override_db():
        yield fake_db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    yield doc

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_ai_stream_returns_progressive_sse_chunks(client, _ai_stream_setup, monkeypatch):
    doc = _ai_stream_setup

    import app.api.v1.ai as ai_api

    async def _fake_stream(*_args, **_kwargs):
        yield "Première phrase. Deuxième"
        yield " phrase. Troisième"

    async def _allow_privacy_gate(*_args, **_kwargs):
        return {"decision": "allow"}

    async def _allow_prompt(text: str):
        return text, {"verdict": "allow"}

    async def _allow_response(text: str):
        return text, {"verdict": "allow"}

    monkeypatch.setattr(ai_api, "_select_llm_provider", lambda _provider: "mistral")
    monkeypatch.setattr(ai_api, "stream_mistral_response", _fake_stream)
    monkeypatch.setattr(ai_api, "require_privacy_gate", _allow_privacy_gate)
    monkeypatch.setattr(ai_api, "guard_outbound_prompt", _allow_prompt)
    monkeypatch.setattr(ai_api, "guard_inbound_response", _allow_response)

    resp = await client.post(
        f"/api/v1/ai/stream/{doc.id}?question=résume",
        headers={"Authorization": "Bearer fake-token"},
    )

    assert resp.status_code == 200
    body = resp.text
    assert body.count('"chunk"') >= 3
    assert "Première phrase." in body
    assert "Deuxième phrase." in body
    assert "Troisième" in body
    assert "data: [DONE]" in body


@pytest.mark.asyncio
async def test_ai_stream_scans_split_identifier_before_restitution(
    client, _ai_stream_setup, monkeypatch
):
    doc = _ai_stream_setup

    import app.api.v1.ai as ai_api

    scanned_segments: list[str] = []

    async def _fake_stream(*_args, **_kwargs):
        yield "Le contact est marie."
        yield "martin@cabinet.fr. Réponse terminée."

    async def _allow_privacy_gate(*_args, **_kwargs):
        return {"decision": "allow"}

    async def _allow_prompt(text: str):
        return text, {"verdict": "allow"}

    async def _scan_response(text: str):
        scanned_segments.append(text)
        if "marie.martin@cabinet.fr" in text:
            return text.replace("marie.martin@cabinet.fr", "[EMAIL]"), {"verdict": "redact"}
        return text, {"verdict": "allow"}

    monkeypatch.setattr(ai_api, "_select_llm_provider", lambda _provider: "mistral")
    monkeypatch.setattr(ai_api, "stream_mistral_response", _fake_stream)
    monkeypatch.setattr(ai_api, "require_privacy_gate", _allow_privacy_gate)
    monkeypatch.setattr(ai_api, "guard_outbound_prompt", _allow_prompt)
    monkeypatch.setattr(ai_api, "guard_inbound_response", _scan_response)

    resp = await client.post(
        f"/api/v1/ai/stream/{doc.id}?question=contact",
        headers={"Authorization": "Bearer fake-token"},
    )

    assert resp.status_code == 200
    assert "marie.martin@cabinet.fr" not in resp.text
    assert "[EMAIL]" in resp.text
    assert any("marie.martin@cabinet.fr" in segment for segment in scanned_segments)
