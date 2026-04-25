"""Tests for startup database compatibility migrations."""


def test_document_status_enum_startup_migration_contains_pipeline_statuses():
    from app.core.database import DOCUMENT_STATUS_ENUM_VALUES

    assert "EXTRACTING" in DOCUMENT_STATUS_ENUM_VALUES
    assert "EXTRACTED" in DOCUMENT_STATUS_ENUM_VALUES
    assert "ANONYMIZING" in DOCUMENT_STATUS_ENUM_VALUES
    assert "READY" in DOCUMENT_STATUS_ENUM_VALUES


def test_metadata_registers_pseudonym_mappings_table():
    from app.models import Base

    assert "pseudonym_mappings" in Base.metadata.tables


def test_metadata_registers_document_chunks_table():
    from app.models import Base

    assert "document_chunks" in Base.metadata.tables
