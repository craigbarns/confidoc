"""Tests API des routes /documents (via ASGI client).

Couvre :
- Toutes les routes exigent une authentification (401 sans token)
- Structure des routes déclarées dans le router assemblé
- Réponses 401/422 selon les cas d'utilisation
- Routes statiques déclarées avant les routes dynamiques (ordre important)
"""

from __future__ import annotations

import pytest


# ══════════════════════════════════════════════════════════════════════
# Routes déclarées (structure)
# ══════════════════════════════════════════════════════════════════════

class TestDocumentsRouterStructure:
    """Vérifie que toutes les routes attendues sont bien enregistrées."""

    def _get_paths(self):
        from app.api.v1.documents import router
        return [r.path for r in router.routes]

    def test_list_route_exists(self):
        paths = self._get_paths()
        assert "/" in paths

    def test_clients_route_exists(self):
        paths = self._get_paths()
        assert "/clients" in paths

    def test_trash_list_route_exists(self):
        paths = self._get_paths()
        assert "/trash/list" in paths

    def test_delete_all_route_exists(self):
        paths = self._get_paths()
        assert "/all" in paths

    def test_stats_dashboard_route_exists(self):
        paths = self._get_paths()
        assert "/stats/dashboard" in paths

    def test_status_summary_route_exists(self):
        paths = self._get_paths()
        assert "/status-summary" in paths

    def test_document_by_id_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}" in paths

    def test_restore_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/restore" in paths

    def test_permanent_delete_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/permanent" in paths

    def test_extract_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/extract" in paths

    def test_anonymize_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/anonymize" in paths

    def test_preview_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/preview" in paths

    def test_validate_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/validate" in paths

    def test_approve_export_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/approve-export" in paths

    def test_export_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/export" in paths

    def test_audit_report_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/audit-report" in paths

    def test_risk_score_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/risk-score" in paths

    def test_compliance_report_route_exists(self):
        paths = self._get_paths()
        assert "/{document_id}/compliance-report" in paths

    def test_no_duplicate_method_path_routes(self):
        """Un même (method, path) ne doit pas apparaître deux fois."""
        from fastapi.routing import APIRoute
        from app.api.v1.documents import router
        seen: set[tuple] = set()
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods or []:
                key = (method, route.path)
                assert key not in seen, f"Route dupliquée : {method} {route.path}"
                seen.add(key)

    def test_static_routes_before_dynamic(self):
        """Les routes statiques (/clients, /trash/list) doivent être déclarées AVANT /{document_id}."""
        paths = self._get_paths()
        dynamic_idx = next((i for i, p in enumerate(paths) if p == "/{document_id}"), None)
        assert dynamic_idx is not None, "Route /{document_id} introuvable"

        for static in ("/clients", "/trash/list", "/all", "/stats/dashboard", "/status-summary"):
            if static in paths:
                static_idx = paths.index(static)
                assert static_idx < dynamic_idx, (
                    f"Route statique {static!r} (idx={static_idx}) doit être avant "
                    f"'/{'{document_id}'}' (idx={dynamic_idx})"
                )


# ══════════════════════════════════════════════════════════════════════
# Authentication requise (401 sans token)
# ══════════════════════════════════════════════════════════════════════

class TestDocumentsAuthRequired:
    """Toutes les routes protégées doivent retourner 401 sans JWT."""

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_clients_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/clients")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_trash_list_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/trash/list")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_dashboard_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/stats/dashboard")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_status_summary_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/status-summary")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_document_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/some-fake-uuid")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_extract_requires_auth(self, client):
        resp = await client.post("/api/v1/documents/some-fake-uuid/extract")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_anonymize_requires_auth(self, client):
        resp = await client.post("/api/v1/documents/some-fake-uuid/anonymize")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/some-fake-uuid/export")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_audit_report_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/some-fake-uuid/audit-report")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_risk_score_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/some-fake-uuid/risk-score")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_all_requires_auth(self, client):
        resp = await client.delete("/api/v1/documents/all")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_restore_requires_auth(self, client):
        resp = await client.post("/api/v1/documents/some-fake-uuid/restore")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_permanent_delete_requires_auth(self, client):
        resp = await client.delete("/api/v1/documents/some-fake-uuid/permanent")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════
# Faux token : 401 (pas 500)
# ══════════════════════════════════════════════════════════════════════

class TestDocumentsFakeToken:
    """Un token invalide doit retourner 401, jamais 500."""

    @pytest.mark.asyncio
    async def test_fake_bearer_returns_401_not_500(self, client):
        resp = await client.get(
            "/api/v1/documents/",
            headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_bearer_returns_401(self, client):
        resp = await client.get(
            "/api/v1/documents/stats/dashboard",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401
