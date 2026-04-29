"""Tests for upload endpoints."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest


class TestUploadValidation:
    """Test file upload validation logic."""

    @pytest.mark.asyncio
    async def test_upload_requires_auth(self, client):
        resp = await client.post("/api/v1/uploads")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_no_file(self, client):
        resp = await client.post(
            "/api/v1/uploads",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code in (401, 422)

    def test_upload_profile_allows_railway_smoke_profiles(self):
        from typing import get_args

        from app.api.v1.uploads import AnonymizationProfile

        profiles = set(get_args(AnonymizationProfile))
        assert "dataset_accounting" in profiles
        assert "dataset_accounting_pseudo" in profiles


class TestUploadExtension:
    """Test extension validation."""

    def test_allowed_extensions_from_config(self):
        from app.config import get_settings

        settings = get_settings()
        assert "pdf" in settings.ALLOWED_EXTENSIONS
        assert "png" in settings.ALLOWED_EXTENSIONS
        assert "exe" not in settings.ALLOWED_EXTENSIONS

    def test_max_upload_size(self):
        from app.config import get_settings

        settings = get_settings()
        assert settings.max_upload_size_bytes == settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        assert settings.max_upload_size_bytes > 0


# ──────────────────────────────────────────────────────────────────────────
# Integration test for the authenticated success path.
#
# Regression guard for PR #18 (commit dfb636c). Before that fix, the upload
# endpoint reached ``db.commit()`` (so a Document row was created) and then
# raised a NameError in the response/logger payload (``normalized_client_name``,
# missing ``http_404`` import) *before* registering the background
# anonymisation task. Symptoms:
#   - API returned 500
#   - Document row stuck in status UPLOADED
#   - Anonymisation pipeline never scheduled → users saw "ça marche pas"
#
# This test mocks the heavy infrastructure (storage, OCR, Celery probe,
# DB) but exercises the *real* route handler, including the response
# building and the call into background_tasks. If the NameError ever
# comes back, this test fails immediately.
# ──────────────────────────────────────────────────────────────────────────


class _EmptyResult:
    """Mimics SQLAlchemy ``Result`` for queries that find nothing."""

    def scalar_one_or_none(self) -> None:
        return None

    def scalars(self) -> "_EmptyResult":
        return self

    def all(self) -> list[Any]:
        return []

    def __iter__(self):  # pragma: no cover — compatibility
        return iter([])


class _MinimalFakeSession:
    """Tiny AsyncSession-like stand-in for the upload happy path.

    Returns an empty result for every query (membership/client/dossier are
    all "not found", so the route exercises the auto-create branches) and
    assigns a UUID to every object passed to ``add()`` so downstream code
    that reads ``client.id`` / ``document.id`` keeps working.
    """

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.commits = 0

    async def execute(self, _stmt: Any) -> _EmptyResult:
        return _EmptyResult()

    def add(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, _obj: Any) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def _upload_overrides():
    """Override ``get_db`` and ``get_current_user`` for the upload route."""
    from app.api.deps import get_current_user
    from app.core.database import get_db
    from app.main import app

    fake_db = _MinimalFakeSession()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        is_active=True,
        email="qa@confidoc.test",
    )

    async def _override_db():
        yield fake_db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    yield app, fake_db, user

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


class TestUploadHappyPath:
    """Regression guard against the PR #18 ``NameError`` before scheduling."""

    @pytest.mark.asyncio
    async def test_authenticated_pdf_upload_returns_201_and_schedules_anonymisation(
        self, client, _upload_overrides, monkeypatch
    ):
        """A real authenticated POST /api/v1/uploads must:

        - return **201** (never 500),
        - expose ``document_id`` / ``original_filename`` / ``client_name`` /
          ``processing.status`` in the JSON body,
        - register the anonymisation background task via
          ``background_tasks.add_task(run_anonymize_document_inline, ...)``.

        Pre-fix behaviour failed steps 1 and 3 because of the ``NameError``
        raised after ``db.commit()`` but before
        ``background_tasks.add_task``.
        """
        import app.api.v1.uploads as uploads_mod
        import app.services.anonymization_service as anon_svc
        from app.rate_limit import limiter

        # The slowapi limiter talks to Redis for storage. In CI / local
        # tests Redis is not available — toggle it off for this single
        # request and restore it afterwards.
        monkeypatch.setattr(limiter, "enabled", False)

        # ── Mock infrastructure unrelated to the regression we test ──
        monkeypatch.setattr(uploads_mod, "scan_file_for_malware", lambda *a, **k: None)
        monkeypatch.setattr(
            uploads_mod,
            "store_file",
            lambda **kw: ("database", "db://qa-test.pdf"),
        )
        monkeypatch.setattr(
            uploads_mod,
            "should_dispatch_document_task_to_celery",
            lambda **kw: False,
        )
        # OCR/text extraction is heavy and irrelevant here.
        async def _empty_extract(_data, _ext):
            return ""

        monkeypatch.setattr(anon_svc, "extract_text_from_file", _empty_extract)

        # ── Capture the anonymisation scheduling call ──
        scheduled: list[dict[str, Any]] = []

        def _fake_inline_anonymize(**kwargs):
            scheduled.append(kwargs)

        monkeypatch.setattr(
            uploads_mod,
            "run_anonymize_document_inline",
            _fake_inline_anonymize,
        )

        # Minimal valid PDF bytes: header + EOF marker is enough for the
        # MIME sniff in scan_file_for_malware (already mocked above).
        pdf_bytes = b"%PDF-1.4\n%fake confidoc qa\n%%EOF"
        files = {"file": ("invoice_qa.pdf", pdf_bytes, "application/pdf")}

        response = await client.post(
            "/api/v1/uploads",
            params={"client_name": "ACME SAS QA"},
            files=files,
        )

        # 1. The endpoint did not 500 — this is the regression guard.
        assert response.status_code == 201, (
            f"Upload happy path must return 201, got "
            f"{response.status_code}: {response.text}"
        )

        body = response.json()

        # 2. Response shape carries the fields the UI/idempotency layer rely on.
        assert "document_id" in body and body["document_id"]
        assert body["original_filename"] == "invoice_qa.pdf"
        assert body["client_name"] == "ACME SAS QA"
        assert "processing" in body
        assert body["processing"]["status"] == "processing"

        # 3. Anonymisation scheduling actually happened. Without this, the
        #    document would stay stuck in UPLOADED forever — exactly the
        #    pre-PR-#18 symptom.
        assert len(scheduled) == 1, (
            "run_anonymize_document_inline must be scheduled exactly once. "
            "Pre-fix code raised NameError before reaching this call."
        )
        assert scheduled[0]["doc_id"] == body["document_id"]
