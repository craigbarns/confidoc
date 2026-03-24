"""Tests for org-level document endpoints."""


class TestOrgEndpointsRegistered:
    """Test that org-level endpoints are properly registered."""

    def test_org_list_endpoint_exists(self):
        from app.api.v1.documents import router
        routes = [r.path for r in router.routes]
        assert "/org" in routes

    def test_org_stats_endpoint_exists(self):
        from app.api.v1.documents import router
        routes = [r.path for r in router.routes]
        assert "/org/stats" in routes

    def test_trash_endpoint_exists(self):
        from app.api.v1.documents import router
        routes = [r.path for r in router.routes]
        assert "/trash" in routes

    def test_restore_endpoint_exists(self):
        from app.api.v1.documents import router
        routes = [r.path for r in router.routes]
        assert "/{document_id}/restore" in routes

    def test_csv_export_endpoint_exists(self):
        from app.api.v1.documents import router
        routes = [r.path for r in router.routes]
        assert "/{document_id}/export-csv" in routes


class TestGetUserOrgId:
    """Test the _get_user_org_id helper."""

    def test_function_exists(self):
        from app.api.v1.documents import _get_user_org_id
        assert callable(_get_user_org_id)
