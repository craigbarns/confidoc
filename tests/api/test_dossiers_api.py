"""Tests API routes /documents/dossiers et /{id}/metadata."""

import pytest


class TestDossiersRoutes:
    """Vérifie que les nouvelles routes sont bien enregistrées."""

    def _get_paths(self):
        from app.api.v1.documents import router
        return [r.path for r in router.routes]

    def test_dossiers_route_exists(self):
        assert "/dossiers" in self._get_paths()

    def test_metadata_patch_route_exists(self):
        assert "/{document_id}/metadata" in self._get_paths()

    def test_dossiers_route_before_document_id(self):
        paths = self._get_paths()
        dossiers_idx = next(i for i, p in enumerate(paths) if p == "/dossiers")
        doc_id_idx = next(i for i, p in enumerate(paths) if p == "/{document_id}")
        assert dossiers_idx < doc_id_idx, "/dossiers doit être avant /{document_id}"


class TestDossiersAuth:
    """Vérifie que les nouvelles routes exigent une authentification."""

    @pytest.mark.asyncio
    async def test_get_dossiers_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/dossiers")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_patch_metadata_requires_auth(self, client):
        resp = await client.patch(
            "/api/v1/documents/00000000-0000-0000-0000-000000000001/metadata",
            json={"exercice": "2024"},
        )
        assert resp.status_code == 401


class TestDocumentResponseSchema:
    """Vérifie que DocumentResponse inclut les nouveaux champs."""

    def test_client_name_field_exists(self):
        from app.schemas.document import DocumentResponse
        assert "client_name" in DocumentResponse.model_fields

    def test_exercice_field_exists(self):
        from app.schemas.document import DocumentResponse
        assert "exercice" in DocumentResponse.model_fields

    def test_doc_category_field_exists(self):
        from app.schemas.document import DocumentResponse
        assert "doc_category" in DocumentResponse.model_fields


class TestDocumentMetadataPatchSchema:
    """Vérifie la validation du schéma DocumentMetadataPatch."""

    def test_valid_exercice(self):
        from app.schemas.document import DocumentMetadataPatch
        p = DocumentMetadataPatch(exercice="2024")
        assert p.exercice == "2024"

    def test_invalid_exercice_format(self):
        from pydantic import ValidationError
        from app.schemas.document import DocumentMetadataPatch
        with pytest.raises(ValidationError):
            DocumentMetadataPatch(exercice="24")

    def test_all_none_is_valid(self):
        from app.schemas.document import DocumentMetadataPatch
        p = DocumentMetadataPatch()
        assert p.client_name is None
        assert p.exercice is None
        assert p.doc_category is None
