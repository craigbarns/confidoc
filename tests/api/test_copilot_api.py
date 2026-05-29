"""API tests for the Copilot security gate and validation rules."""

import uuid
from typing import Any
import pytest

from app.models.document import Document, DocumentStatus
from app.models.document_version import DocumentVersion, DocumentVersionType
from app.models.pseudonym_mapping import PseudonymMapping
from app.api.deps import get_current_user, get_db
from app.main import app


class _FakeResult:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def all(self) -> list[Any]:
        return [self._value] if self._value is not None else []


class _FakeDb:
    def __init__(self, document: Document, version: DocumentVersion, mapping: PseudonymMapping) -> None:
        self.document = document
        self.version = version
        self.mapping = mapping
        self.added = []
        self.commits = 0

    async def execute(self, stmt: Any) -> Any:
        stmt_str = str(stmt).lower()
        if "from documents" in stmt_str:
            return _FakeResult(self.document)
        elif "from document_versions" in stmt_str:
            return _FakeResult(self.version)
        elif "from pseudonym_mappings" in stmt_str:
            return _FakeResult(self.mapping)
        elif "from entity_detections" in stmt_str:
            return _FakeResult(None)
        elif "from audit_logs" in stmt_str:
            class _CountResult:
                def scalar(self):
                    return 3
            return _CountResult()
        return _FakeResult(None)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


@pytest.fixture
def _copilot_setup(monkeypatch):
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    
    user = type("User", (), {
        "id": user_id,
        "org_id": org_id,
        "is_active": True,
        "email": "qa@confidoc.test",
    })()

    doc = Document(
        id=doc_id,
        org_id=org_id,
        uploaded_by_user_id=user_id,
        original_filename="audit_comptable.pdf",
        content_type="application/pdf",
        extension="pdf",
        size_bytes=1024,
        sha256="abc" * 20,
        storage_backend="local",
        storage_key=f"uploads/{doc_id}.pdf",
        status=DocumentStatus.READY,
    )

    version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc_id,
        version_type=DocumentVersionType.FINAL_ANONYMIZED,
        content_text="Le chiffre d'affaires de la société [SOCIETE_1] est confidentiel.",
    )

    mapping = PseudonymMapping(
        id=uuid.uuid4(),
        document_id=doc_id,
        user_id=user_id,
        encrypted_mapping="fake-encrypted-blob",
        risk_score=0.45,
        risk_level="medium",
        human_validated=False,
        autopilot_validated=False,
    )

    fake_db = _FakeDb(doc, version, mapping)

    async def _override_db():
        yield fake_db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    # Mock the LLM service to avoid outgoing requests
    import app.services.copilot_service as copilot_svc
    async def _mock_summary(*args, **kwargs):
        return {"validated": {"resume_executif": "Réponse du Copilot.", "points_cles": ["Point 1"]}}
    monkeypatch.setattr(copilot_svc, "generate_summary_with_mistral", _mock_summary)

    # These tests exercise the DPO Privacy Gate for EXTERNAL AI use. Force the
    # external action so the gate's decision is deterministic regardless of whether
    # Mistral is configured in the environment (CI has no Mistral key).
    import app.api.v1.copilot as copilot_api
    monkeypatch.setattr(copilot_api, "_copilot_privacy_action", lambda: "external_ai")

    yield app, fake_db, doc, version, mapping

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_copilot_ask_blocked_if_medium_risk_and_no_validation(client, _copilot_setup) -> None:
    _, _, doc, _, _ = _copilot_setup
    
    # 1. Medium risk, no validation -> should block
    resp = await client.post(
        f"/api/v1/copilot/{doc.id}/ask",
        headers={"Authorization": "Bearer fake-token"},
        json={"question": "Quel est le chiffre d'affaires ?"},
    )
    assert resp.status_code == 400
    assert "Privacy Gate DPO" in resp.json()["detail"]
    assert "Risque moyen pour un usage externe" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_copilot_ask_allowed_if_medium_risk_and_autopilot_validated(client, _copilot_setup) -> None:
    _, _, doc, _, mapping = _copilot_setup
    
    # 2. Medium risk, autopilot validated -> allowed but with warning
    mapping.autopilot_validated = True
    
    resp = await client.post(
        f"/api/v1/copilot/{doc.id}/ask",
        headers={"Authorization": "Bearer fake-token"},
        json={"question": "Quel est le chiffre d'affaires ?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Réponse du Copilot" in body["answer"]
    assert any("validation humaine recommandée" in w for w in body["warnings"])


@pytest.mark.asyncio
async def test_copilot_ask_allowed_if_medium_risk_and_human_validated(client, _copilot_setup) -> None:
    _, _, doc, _, mapping = _copilot_setup
    
    # 3. Medium risk, human validated -> allowed, no autopilot warnings
    mapping.human_validated = True
    
    resp = await client.post(
        f"/api/v1/copilot/{doc.id}/ask",
        headers={"Authorization": "Bearer fake-token"},
        json={"question": "Quel est le chiffre d'affaires ?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Réponse du Copilot" in body["answer"]
    assert not any("validation humaine recommandée" in w for w in body["warnings"])


@pytest.mark.asyncio
async def test_copilot_ask_blocked_if_high_risk_and_autopilot_validated(client, _copilot_setup) -> None:
    _, _, doc, _, mapping = _copilot_setup
    
    # 4. High risk, autopilot validated -> should STILL block
    mapping.risk_level = "high"
    mapping.autopilot_validated = True
    
    resp = await client.post(
        f"/api/v1/copilot/{doc.id}/ask",
        headers={"Authorization": "Bearer fake-token"},
        json={"question": "Quel est le chiffre d'affaires ?"},
    )
    assert resp.status_code == 400
    assert "Risque élevé sans validation humaine DPO" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_copilot_ask_allowed_if_high_risk_and_human_validated(client, _copilot_setup) -> None:
    _, _, doc, _, mapping = _copilot_setup
    
    # 5. High risk, human validated -> allowed
    mapping.risk_level = "high"
    mapping.human_validated = True
    
    resp = await client.post(
        f"/api/v1/copilot/{doc.id}/ask",
        headers={"Authorization": "Bearer fake-token"},
        json={"question": "Quel est le chiffre d'affaires ?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Réponse du Copilot" in body["answer"]
