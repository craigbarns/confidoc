"""Tests pour upload batch et routes documents."""

import pytest

from app.api.v1.uploads import MAX_BATCH_SIZE


def test_max_batch_size_configured():
    assert MAX_BATCH_SIZE == 20
    assert MAX_BATCH_SIZE > 0


class TestDocumentModelSoftDelete:
    def test_is_deleted_column_exists(self):
        from app.models.document import Document

        cols = {c.name for c in Document.__table__.columns}
        assert "is_deleted" in cols
        assert "deleted_at" in cols


class TestRoutes:
    def test_anonymize_route_exists(self):
        from app.api.v1.documents import router

        routes = [r.path for r in router.routes]
        assert "/{document_id}/anonymize" in routes

    def test_preview_route_exists(self):
        from app.api.v1.documents import router

        routes = [r.path for r in router.routes]
        assert "/{document_id}/preview" in routes

    def test_export_route_exists(self):
        from app.api.v1.documents import router

        routes = [r.path for r in router.routes]
        assert "/{document_id}/export" in routes

    def test_batch_endpoint_route_exists(self):
        from app.api.v1.uploads import router

        routes = [r.path for r in router.routes]
        assert "/batch" in routes

    def test_copilot_compare_route_exists(self):
        from app.api.v1.copilot import router

        routes = [r.path for r in router.routes]
        assert "/{document_id}/compare" in routes
