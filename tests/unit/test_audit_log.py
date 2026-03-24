"""Tests for audit log model and middleware helpers."""

from app.models.audit_log import AuditLog
from app.audit import _extract_resource, _extract_action


class TestAuditLogModel:
    """Test the AuditLog model structure."""

    def test_table_name(self):
        assert AuditLog.__tablename__ == "audit_logs"

    def test_has_required_columns(self):
        cols = {c.name for c in AuditLog.__table__.columns}
        assert "user_id" in cols
        assert "org_id" in cols
        assert "action" in cols
        assert "resource_type" in cols
        assert "resource_id" in cols
        assert "method" in cols
        assert "path" in cols
        assert "status_code" in cols
        assert "ip_address" in cols
        assert "details" in cols

    def test_action_is_indexed(self):
        col = AuditLog.__table__.columns["action"]
        assert col.index is True

    def test_resource_type_is_indexed(self):
        col = AuditLog.__table__.columns["resource_type"]
        assert col.index is True


class TestExtractResource:
    """Test resource extraction from paths."""

    def test_document_with_id(self):
        rtype, rid = _extract_resource("/api/v1/documents/550e8400-e29b-41d4-a716-446655440000")
        assert rtype == "document"
        assert rid == "550e8400-e29b-41d4-a716-446655440000"

    def test_upload_path(self):
        rtype, rid = _extract_resource("/api/v1/uploads")
        assert rtype == "upload"

    def test_auth_path(self):
        rtype, rid = _extract_resource("/api/v1/auth/token")
        assert rtype == "auth"

    def test_feedback_path(self):
        rtype, rid = _extract_resource("/api/v1/feedback")
        assert rtype == "feedback"

    def test_unknown_path(self):
        rtype, rid = _extract_resource("/api/v1/something-else")
        assert rtype == "unknown"


class TestExtractAction:
    """Test action derivation from method + path."""

    def test_login(self):
        assert _extract_action("POST", "/api/v1/auth/token") == "login"

    def test_register(self):
        assert _extract_action("POST", "/api/v1/auth/register") == "register"

    def test_anonymize(self):
        assert _extract_action("POST", "/api/v1/documents/123/anonymize") == "anonymize"

    def test_validate(self):
        assert _extract_action("POST", "/api/v1/documents/123/validate") == "validate"

    def test_export(self):
        assert _extract_action("GET", "/api/v1/documents/123/export-csv") == "export"

    def test_restore(self):
        assert _extract_action("POST", "/api/v1/documents/123/restore") == "restore"

    def test_batch_upload(self):
        assert _extract_action("POST", "/api/v1/uploads/batch") == "batch_upload"

    def test_generic_post(self):
        assert _extract_action("POST", "/api/v1/something") == "create"

    def test_generic_delete(self):
        assert _extract_action("DELETE", "/api/v1/something") == "delete"

    def test_generic_put(self):
        assert _extract_action("PUT", "/api/v1/something") == "update"

    def test_feedback_submit(self):
        assert _extract_action("POST", "/api/v1/feedback") == "feedback_submit"
