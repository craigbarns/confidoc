"""Tests for soft delete functionality on Document model."""

from datetime import datetime, timezone

import pytest

from app.models.base import SoftDeleteMixin
from app.models.document import Document, DocumentStatus


class TestSoftDeleteMixin:
    """Test the SoftDeleteMixin behavior."""

    def test_document_has_soft_delete_fields(self):
        """Document model should have is_deleted and deleted_at fields."""
        assert hasattr(Document, "is_deleted")
        assert hasattr(Document, "deleted_at")

    def test_document_inherits_soft_delete_mixin(self):
        """Document should inherit from SoftDeleteMixin."""
        assert issubclass(Document, SoftDeleteMixin)

    def test_is_deleted_default_false(self):
        """is_deleted should default to False."""
        col = Document.__table__.columns["is_deleted"]
        assert col.server_default is not None
        assert str(col.server_default.arg) == "false"

    def test_deleted_at_nullable(self):
        """deleted_at should be nullable (None when not deleted)."""
        col = Document.__table__.columns["deleted_at"]
        assert col.nullable is True

    def test_is_deleted_indexed(self):
        """is_deleted should be indexed for query performance."""
        col = Document.__table__.columns["is_deleted"]
        assert col.index is True


class TestDocumentCompositeIndexes:
    """Test composite indexes on Document model."""

    def test_user_created_index_exists(self):
        """Composite index on (uploaded_by_user_id, created_at) should exist."""
        index_names = {idx.name for idx in Document.__table__.indexes}
        assert "ix_documents_user_created" in index_names

    def test_org_created_index_exists(self):
        """Composite index on (org_id, created_at) should exist."""
        index_names = {idx.name for idx in Document.__table__.indexes}
        assert "ix_documents_org_created" in index_names

    def test_user_active_index_exists(self):
        """Composite index on (uploaded_by_user_id, is_deleted) should exist."""
        index_names = {idx.name for idx in Document.__table__.indexes}
        assert "ix_documents_user_active" in index_names

    def test_org_status_index_exists(self):
        """Composite index on (org_id, status) should exist."""
        index_names = {idx.name for idx in Document.__table__.indexes}
        assert "ix_documents_org_status" in index_names
