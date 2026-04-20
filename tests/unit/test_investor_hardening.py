"""Regression tests for due-diligence hardening guarantees."""

import inspect

import pytest


def test_celery_tasks_do_not_accept_raw_file_bytes():
    from app.workers.tasks import anonymize_document_task, process_document_legacy_task

    anonymize_params = inspect.signature(anonymize_document_task.run).parameters
    legacy_params = inspect.signature(process_document_legacy_task.run).parameters

    assert "content" not in anonymize_params
    assert "file_content" not in legacy_params
    assert "doc_id" in anonymize_params
    assert "doc_id" in legacy_params


def test_audit_resource_extracts_public_leads():
    from app.audit import _extract_resource

    resource_type, resource_id = _extract_resource("/api/v1/leads/beta")
    assert resource_type == "lead"
    assert resource_id is None


def test_document_bytes_fallback_reads_database_raw_content():
    from types import SimpleNamespace

    from app.services.storage_service import read_document_bytes

    document = SimpleNamespace(
        id="doc-1",
        storage_backend="database",
        storage_key="db://doc-1",
        raw_content=b"private-pdf-bytes",
    )

    assert read_document_bytes(document) == b"private-pdf-bytes"


def test_production_rejects_ephemeral_local_storage():
    from app.config import Settings

    with pytest.raises(ValueError, match="STORAGE_BACKEND=local"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="x" * 64,
            JWT_SECRET_KEY="y" * 64,
            ENCRYPTION_MASTER_KEY="z" * 44,
            PSEUDO_MAPPING_KEY="w" * 44,
            STORAGE_BACKEND="local",
        )
