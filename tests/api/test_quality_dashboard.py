"""Tests for ``GET /api/v1/stats/quality-dashboard``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest


# ──────────────────────────────────────────────────────────────────────
# Route registration & auth
# ──────────────────────────────────────────────────────────────────────


def test_quality_dashboard_route_registered():
    from app.api.v1._doc_stats import router

    paths = [r.path for r in router.routes]
    assert "/quality-dashboard" in paths


def test_quality_dashboard_route_registered_in_v1_under_stats():
    from app.api.v1.router import router

    paths = [getattr(r, "path", "") for r in router.routes]
    assert any(p.endswith("/stats/quality-dashboard") for p in paths)


@pytest.mark.asyncio
async def test_quality_dashboard_requires_auth(client):
    resp = await client.get("/api/v1/stats/quality-dashboard")
    assert resp.status_code == 401


# ──────────────────────────────────────────────────────────────────────
# Service-level tests: pure-Python aggregation logic
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_quality_metrics_returns_empty_when_no_org():
    from app.services.quality_metrics_service import compute_quality_metrics

    metrics = await compute_quality_metrics(db=None, org_id=None)  # type: ignore[arg-type]
    assert metrics.org_id is None
    assert metrics.total_documents == 0
    assert metrics.processed_documents == 0
    assert metrics.validated_documents == 0
    assert metrics.avg_processing_seconds is None
    assert metrics.avg_time_to_validation_seconds is None
    assert metrics.one_shot_full_ready_rate is None
    assert metrics.avg_human_overrides_per_document is None
    assert metrics.total_golden_case_drafts == 0
    assert metrics.accepted_golden_case_drafts == 0
    assert metrics.corrections_by_field == {}
    assert metrics.corrections_by_error_type == {}
    assert metrics.documents_by_status == {}


@pytest.mark.asyncio
async def test_compute_quality_metrics_aggregates_known_values(monkeypatch):
    """Stub each helper and verify the assembled response."""
    from app.services import quality_metrics_service as svc

    org_id = uuid.uuid4()
    sentinel_db = object()
    seen_org_ids: list[uuid.UUID] = []

    async def fake_count_documents(db, oid):
        seen_org_ids.append(oid)
        return 10, {"ready": 6, "uploaded": 3, "failed": 1}

    async def fake_processed_validated(db, oid):
        seen_org_ids.append(oid)
        return 8, 6

    async def fake_avg(db, oid, version_type):
        seen_org_ids.append(oid)
        from app.models.document_version import DocumentVersionType

        if version_type == DocumentVersionType.PREVIEW_ANONYMIZED:
            return 12.5
        if version_type == DocumentVersionType.FINAL_ANONYMIZED:
            return 240.0
        return None

    async def fake_drafts(db, oid):
        seen_org_ids.append(oid)
        return (
            9,
            4,
            {"total_ttc": 5, "siret": 4},
            {"manual_correction": 7, "missed_field": 2},
        )

    async def fake_validated_with_drafts(db, oid):
        seen_org_ids.append(oid)
        return 3  # 3 of 6 validated docs needed at least one correction

    monkeypatch.setattr(svc, "_count_documents", fake_count_documents)
    monkeypatch.setattr(
        svc, "_count_processed_and_validated", fake_processed_validated
    )
    monkeypatch.setattr(svc, "_avg_durations_seconds", fake_avg)
    monkeypatch.setattr(svc, "_draft_aggregates", fake_drafts)
    monkeypatch.setattr(
        svc,
        "_count_validated_documents_with_drafts",
        fake_validated_with_drafts,
    )

    metrics = await svc.compute_quality_metrics(sentinel_db, org_id)  # type: ignore[arg-type]

    # Org isolation: every helper must have been called with the caller's org_id.
    assert all(o == org_id for o in seen_org_ids)

    assert metrics.org_id == org_id
    assert metrics.total_documents == 10
    assert metrics.processed_documents == 8
    assert metrics.validated_documents == 6
    assert metrics.avg_processing_seconds == 12.5
    assert metrics.avg_time_to_validation_seconds == 240.0
    assert metrics.total_golden_case_drafts == 9
    assert metrics.accepted_golden_case_drafts == 4
    assert metrics.corrections_by_field == {"total_ttc": 5, "siret": 4}
    assert metrics.corrections_by_error_type == {
        "manual_correction": 7,
        "missed_field": 2,
    }
    assert metrics.documents_by_status == {
        "ready": 6,
        "uploaded": 3,
        "failed": 1,
    }
    # 9 drafts spread over 6 validated docs → 1.5 overrides per validated doc.
    assert metrics.avg_human_overrides_per_document == 1.5
    # 6 validated, 3 needed corrections → one-shot rate = 3/6 = 0.5.
    assert metrics.one_shot_full_ready_rate == 0.5


@pytest.mark.asyncio
async def test_compute_quality_metrics_no_validation_yields_null_ratios(
    monkeypatch,
):
    from app.services import quality_metrics_service as svc

    org_id = uuid.uuid4()

    async def fake_count_documents(db, oid):
        return 5, {"uploaded": 5}

    async def fake_processed_validated(db, oid):
        return 0, 0

    async def fake_avg(db, oid, version_type):
        return None

    async def fake_drafts(db, oid):
        return 0, 0, {}, {}

    async def fake_validated_with_drafts(db, oid):
        return 0

    monkeypatch.setattr(svc, "_count_documents", fake_count_documents)
    monkeypatch.setattr(
        svc, "_count_processed_and_validated", fake_processed_validated
    )
    monkeypatch.setattr(svc, "_avg_durations_seconds", fake_avg)
    monkeypatch.setattr(svc, "_draft_aggregates", fake_drafts)
    monkeypatch.setattr(
        svc, "_count_validated_documents_with_drafts", fake_validated_with_drafts
    )

    metrics = await svc.compute_quality_metrics(object(), org_id)  # type: ignore[arg-type]

    assert metrics.total_documents == 5
    assert metrics.validated_documents == 0
    assert metrics.avg_processing_seconds is None
    assert metrics.avg_time_to_validation_seconds is None
    assert metrics.one_shot_full_ready_rate is None
    assert metrics.avg_human_overrides_per_document is None


# ──────────────────────────────────────────────────────────────────────
# End-to-end route tests with dependency overrides
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_with_overrides():
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    state: dict[str, Any] = {"user": None}

    async def _override_db():
        # The route doesn't actually touch the DB in these tests because the
        # service is monkeypatched at the test site.
        yield SimpleNamespace()

    async def _override_user():
        if state["user"] is None:
            raise RuntimeError("set_user not called")
        return state["user"]

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db

    def set_user(org_id: uuid.UUID | None) -> None:
        state["user"] = SimpleNamespace(
            id=uuid.uuid4(), org_id=org_id, is_active=True
        )

    yield app, set_user

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_route_returns_empty_for_user_without_org(
    app_with_overrides, client, monkeypatch
):
    from app.api.v1 import _doc_stats as stats_mod

    captured: dict[str, Any] = {}

    async def fake_compute(db, org_id):
        captured["org_id"] = org_id
        from app.services.quality_metrics_service import QualityMetrics

        return QualityMetrics(org_id=org_id, as_of=datetime.now(UTC))

    monkeypatch.setattr(stats_mod, "compute_quality_metrics", fake_compute)

    _, set_user = app_with_overrides
    set_user(None)

    resp = await client.get("/api/v1/stats/quality-dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert captured["org_id"] is None
    assert body["org_id"] is None
    assert body["total_documents"] == 0
    assert body["validated_documents"] == 0
    assert body["avg_processing_seconds"] is None
    assert body["one_shot_full_ready_rate"] is None
    assert body["corrections_by_field"] == {}
    assert body["corrections_by_error_type"] == {}
    assert body["documents_by_status"] == {}


@pytest.mark.asyncio
async def test_route_passes_only_caller_org_id(
    app_with_overrides, client, monkeypatch
):
    """The route must hand the caller's org_id to the service — never a
    different org's id (no cross-tenant leak)."""
    from app.api.v1 import _doc_stats as stats_mod

    org_id = uuid.uuid4()
    captured: dict[str, Any] = {}

    async def fake_compute(db, oid):
        captured["org_id"] = oid
        from app.services.quality_metrics_service import QualityMetrics

        return QualityMetrics(
            org_id=oid,
            as_of=datetime.now(UTC),
            total_documents=4,
            processed_documents=3,
            validated_documents=2,
            avg_processing_seconds=10.0,
            avg_time_to_validation_seconds=200.0,
            one_shot_full_ready_rate=1.0,
            avg_human_overrides_per_document=0.0,
            total_golden_case_drafts=0,
            accepted_golden_case_drafts=0,
            corrections_by_field={},
            corrections_by_error_type={},
            documents_by_status={"ready": 2, "uploaded": 2},
        )

    monkeypatch.setattr(stats_mod, "compute_quality_metrics", fake_compute)

    _, set_user = app_with_overrides
    set_user(org_id)

    resp = await client.get("/api/v1/stats/quality-dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert captured["org_id"] == org_id
    assert body["org_id"] == str(org_id)
    assert body["total_documents"] == 4
    assert body["one_shot_full_ready_rate"] == 1.0
    assert body["documents_by_status"] == {"ready": 2, "uploaded": 2}


@pytest.mark.asyncio
async def test_route_exposes_grouped_corrections(
    app_with_overrides, client, monkeypatch
):
    from app.api.v1 import _doc_stats as stats_mod

    org_id = uuid.uuid4()

    async def fake_compute(db, oid):
        from app.services.quality_metrics_service import QualityMetrics

        return QualityMetrics(
            org_id=oid,
            as_of=datetime.now(UTC),
            total_documents=3,
            processed_documents=3,
            validated_documents=2,
            avg_processing_seconds=5.0,
            avg_time_to_validation_seconds=120.0,
            one_shot_full_ready_rate=0.5,
            avg_human_overrides_per_document=1.5,
            total_golden_case_drafts=3,
            accepted_golden_case_drafts=1,
            corrections_by_field={"total_ttc": 2, "siret": 1},
            corrections_by_error_type={"wrong_extraction": 2, "missed_field": 1},
            documents_by_status={"ready": 2, "uploaded": 1},
        )

    monkeypatch.setattr(stats_mod, "compute_quality_metrics", fake_compute)

    _, set_user = app_with_overrides
    set_user(org_id)

    resp = await client.get("/api/v1/stats/quality-dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["corrections_by_field"] == {"total_ttc": 2, "siret": 1}
    assert body["corrections_by_error_type"] == {
        "wrong_extraction": 2,
        "missed_field": 1,
    }
    assert body["documents_by_status"] == {"ready": 2, "uploaded": 1}


@pytest.mark.asyncio
async def test_compute_quality_metrics_ai_readiness_and_oneshot_calculation(monkeypatch):
    """Verify exact formula calculations for one-shot rate and AI readiness score."""
    from app.services import quality_metrics_service as svc

    org_id = uuid.uuid4()

    # 1. Base case: 10 documents, 8 processed, 5 validated.
    # 2 validated docs received human correction drafts (out of 5 validated docs).
    # Thus, validated_with_drafts = 2.
    # one_shot_rate should be: (5 - 2) / 5 = 3/5 = 0.60
    # processed_rate = 8 / 10 = 0.8
    # validation_rate = 5 / 10 = 0.5
    # one_shot_component = 0.60
    # accepted_drafts = 1 (gives +5 bonus)
    # failure_penalty = (1 / 10) * 25 = 2.5
    # Expected AI Readiness Score:
    # round(0.8 * 45 + 0.5 * 30 + 0.60 * 20 + 5 - 2.5) = round(36 + 15 + 12 + 5 - 2.5) = round(65.5) = 66
    
    async def fake_count_documents(db, oid):
        return 10, {"ready": 5, "processing": 3, "uploaded": 1, "failed": 1}

    async def fake_processed_validated(db, oid):
        return 8, 5

    async def fake_avg(db, oid, version_type):
        return 10.0

    async def fake_drafts(db, oid):
        return 4, 1, {}, {}

    async def fake_validated_with_drafts(db, oid):
        return 2

    monkeypatch.setattr(svc, "_count_documents", fake_count_documents)
    monkeypatch.setattr(svc, "_count_processed_and_validated", fake_processed_validated)
    monkeypatch.setattr(svc, "_avg_durations_seconds", fake_avg)
    monkeypatch.setattr(svc, "_draft_aggregates", fake_drafts)
    monkeypatch.setattr(svc, "_count_validated_documents_with_drafts", fake_validated_with_drafts)

    metrics = await svc.compute_quality_metrics(None, org_id)  # type: ignore[arg-type]

    assert metrics.one_shot_full_ready_rate == 0.60
    assert metrics.ai_readiness_score == 66
    assert metrics.ai_readiness_level == "internal_review"

