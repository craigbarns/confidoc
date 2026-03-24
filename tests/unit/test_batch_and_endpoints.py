"""Tests for batch upload, CSV export, and restore endpoints."""

import pytest

from app.api.v1.uploads import MAX_BATCH_SIZE


def test_max_batch_size_configured():
    """Batch size limit should be set."""
    assert MAX_BATCH_SIZE == 20
    assert MAX_BATCH_SIZE > 0


class TestCSVExportHelper:
    """Test CSV export utility functions."""

    def test_safe_doc_stem_normal(self):
        from app.api.v1.documents import _safe_doc_stem
        assert _safe_doc_stem("facture_2026.pdf") == "facture_2026"

    def test_safe_doc_stem_special_chars(self):
        from app.api.v1.documents import _safe_doc_stem
        result = _safe_doc_stem("facture (copie) n°3.pdf")
        assert ".pdf" not in result
        assert len(result) > 0

    def test_safe_doc_stem_empty(self):
        from app.api.v1.documents import _safe_doc_stem
        assert _safe_doc_stem("") == "document"

    def test_safe_doc_stem_no_extension(self):
        from app.api.v1.documents import _safe_doc_stem
        result = _safe_doc_stem("filename")
        assert result == "filename"


class TestDocumentModelSoftDeleteIntegration:
    """Test that Document model soft delete works with query patterns."""

    def test_is_deleted_column_exists(self):
        from app.models.document import Document
        cols = {c.name for c in Document.__table__.columns}
        assert "is_deleted" in cols
        assert "deleted_at" in cols

    def test_trash_endpoint_route_exists(self):
        """The /trash endpoint should be registered."""
        from app.api.v1.documents import router
        routes = [r.path for r in router.routes]
        assert "/trash" in routes

    def test_restore_endpoint_route_exists(self):
        """The /{document_id}/restore endpoint should be registered."""
        from app.api.v1.documents import router
        routes = [r.path for r in router.routes]
        assert "/{document_id}/restore" in routes

    def test_csv_export_endpoint_route_exists(self):
        """The /{document_id}/export-csv endpoint should be registered."""
        from app.api.v1.documents import router
        routes = [r.path for r in router.routes]
        assert "/{document_id}/export-csv" in routes


class TestBatchUploadEndpoint:
    """Test batch upload endpoint registration."""

    def test_batch_endpoint_route_exists(self):
        """The /batch endpoint should be registered in uploads router."""
        from app.api.v1.uploads import router
        routes = [r.path for r in router.routes]
        assert "/batch" in routes
