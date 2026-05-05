"""Regression tests for high-risk document export flows."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.v1 import _doc_export
from app.api.v1._doc_shared import _check_export_gate
from app.services.comparison_service import compare_documents


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _FakeDb:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.added: list[Any] = []
        self.commits = 0

    async def execute(self, _stmt: Any) -> _ScalarResult:
        if self.error:
            raise self.error
        return _ScalarResult(self.result)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_export_gate_blocks_high_risk_without_human_validation() -> None:
    document = SimpleNamespace(id=uuid.uuid4())
    user = SimpleNamespace(id=uuid.uuid4())
    mapping = SimpleNamespace(risk_level="high", human_validated=False, risk_score=0.82)

    with pytest.raises(HTTPException) as exc_info:
        await _check_export_gate(_FakeDb(mapping), document, user)

    assert exc_info.value.status_code == 400
    assert "risque eleve" in exc_info.value.detail.lower().replace("é", "e")


@pytest.mark.asyncio
async def test_export_gate_fails_closed_when_compliance_lookup_breaks() -> None:
    document = SimpleNamespace(id=uuid.uuid4())
    user = SimpleNamespace(id=uuid.uuid4())

    with pytest.raises(HTTPException) as exc_info:
        await _check_export_gate(_FakeDb(error=RuntimeError("db unavailable")), document, user)

    assert exc_info.value.status_code == 400
    assert "conformite inaccessible" in exc_info.value.detail


@pytest.mark.asyncio
async def test_export_gate_allows_human_validated_high_risk_mapping() -> None:
    document = SimpleNamespace(id=uuid.uuid4())
    user = SimpleNamespace(id=uuid.uuid4())
    mapping = SimpleNamespace(risk_level="high", human_validated=True, risk_score=0.82)

    await _check_export_gate(_FakeDb(mapping), document, user)


def test_risk_score_percent_normalizes_fractional_and_percent_scores() -> None:
    assert _doc_export._risk_score_percent(None) == 0.0
    assert _doc_export._risk_score_percent(0.82) == 82
    assert _doc_export._risk_score_percent(82) == 82


def test_raw_document_content_disposition_sanitizes_filename() -> None:
    from app.api.v1._doc_crud import _safe_content_disposition_filename

    header = _safe_content_disposition_filename('evil"\r\nX-Bad: 1.pdf')

    assert "\r" not in header
    assert "\n" not in header
    assert "X-Bad:" not in header.split("filename=", 1)[0]
    assert "filename*=" in header


@pytest.mark.asyncio
async def test_export_fec_uses_live_extraction_from_anonymized_text(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    document = SimpleNamespace(
        id=uuid.UUID(document_id),
        org_id=uuid.uuid4(),
        doc_type="facture",
    )
    user = SimpleNamespace(id=uuid.uuid4())
    calls: dict[str, Any] = {}

    async def fake_get_document(
        _db: Any,
        requested_id: str,
        user_id: uuid.UUID,
        permission: str = "documents.read",
    ) -> Any:
        calls["requested_id"] = requested_id
        calls["user_id"] = user_id
        calls["permission"] = permission
        return document

    async def fake_check_gate(_db: Any, checked_document: Any, checked_user: Any) -> None:
        calls["gate_document"] = checked_document
        calls["gate_user"] = checked_user

    async def fake_get_text(_db: Any, checked_document: Any) -> str:
        calls["text_document"] = checked_document
        return "Facture anonymisee total 1200 EUR"

    async def fake_extract(text: str, doc_type: str | None = None) -> dict[str, Any]:
        calls["extract_text"] = text
        calls["doc_type"] = doc_type
        return {
            "type_document": "facture",
            "montants_cles": [
                {"libelle": "Honoraires", "montant": 1200.0, "pcg_code": "622600"}
            ],
        }

    monkeypatch.setattr(_doc_export, "_get_user_document_or_404", fake_get_document)
    monkeypatch.setattr(_doc_export, "_check_export_gate", fake_check_gate)
    monkeypatch.setattr(_doc_export, "_get_anonymized_text", fake_get_text)

    import app.services.llm_extraction_service as extraction_service

    monkeypatch.setattr(extraction_service, "extract_with_llm", fake_extract)

    response = await _doc_export.export_fec(document_id, user, _FakeDb())
    body = response.body.decode()

    assert calls["requested_id"] == document_id
    assert calls["user_id"] == user.id
    assert calls["permission"] == "exports.download"
    assert calls["gate_document"] is document
    assert calls["gate_user"] is user
    assert calls["text_document"] is document
    assert calls["extract_text"] == "Facture anonymisee total 1200 EUR"
    assert calls["doc_type"] == "facture"
    assert body.startswith("JournalCode\tJournalLib\tEcritureNum")
    assert "622600\tHonoraires" in body
    assert "\t1200,00\t0,00\t" in body
    assert "attachment; filename=FEC_" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_compare_documents_accepts_normalized_llm_payload(monkeypatch) -> None:
    async def fake_extract(text: str, doc_type: str | None = None) -> dict[str, Any]:
        assert doc_type == "bilan"
        if text == "current":
            return {
                "exercice": {"date_fin": "31/12/2025"},
                "totaux": {
                    "total_actif": {"montant": 150000.0},
                    "total_passif": {"montant": 149000.0},
                },
                "montants_cles": [
                    {"libelle": "Tresorerie", "montant": 30000.0},
                ],
            }
        return {
            "exercice": {"date_fin": "31/12/2024"},
            "totaux": {
                "total_actif": {"montant": 100000.0},
                "total_passif": {"montant": 100000.0},
            },
            "montants_cles": [
                {"libelle": "Tresorerie", "montant": 10000.0},
            ],
        }

    monkeypatch.setattr("app.services.comparison_service.extract_with_llm", fake_extract)

    result = await compare_documents(_FakeDb(), "current", "previous", doc_type="bilan")
    variations = {item["field"]: item for item in result["variations"]}

    assert variations["total_actif"]["variation_pct"] == 50.0
    assert variations["poste_tresorerie"]["severity"] == "critical"
    assert result["periods"] == {"current": "31/12/2025", "previous": "31/12/2024"}
    assert len(result["coherence_flags"]) == 1
    assert "Actif 150,000" in result["coherence_flags"][0]
    assert "Passif 149,000" in result["coherence_flags"][0]
