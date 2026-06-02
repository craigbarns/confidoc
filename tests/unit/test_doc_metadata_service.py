"""Tests unitaires pour doc_metadata_service."""

import pytest

from app.services.doc_metadata_service import (
    build_metadata_suggestions,
    classify_doc_category,
    extract_exercice,
    suggest_client,
)


class TestExtractExercice:
    def test_bilan_au_31_decembre(self):
        assert extract_exercice("Bilan au 31 décembre 2024") == "2024"

    def test_exercice_clos(self):
        assert extract_exercice("Exercice clos le 31/12/2023") == "2023"

    def test_exercice_bare(self):
        assert extract_exercice("Exercice 2022") == "2022"

    def test_annee_fiscale(self):
        assert extract_exercice("Année fiscale 2021") == "2021"

    def test_au_31_12(self):
        assert extract_exercice("au 31/12/2020") == "2020"

    def test_not_found(self):
        assert extract_exercice("Document sans date") is None

    def test_year_out_of_range(self):
        assert extract_exercice("exercice 1999") is None

    def test_year_future_out_of_range(self):
        assert extract_exercice("exercice 2035") is None


class TestClassifyDocCategory:
    def test_bilan(self):
        result = classify_doc_category(
            "bilan actif passif capitaux propres immobilisations résultat", "bilan.pdf"
        )
        assert result == "bilan"

    def test_releve_bancaire(self):
        result = classify_doc_category(
            "relevé de compte IBAN solde débit crédit virement reçu", "releve.pdf"
        )
        assert result == "releve_bancaire"

    def test_liasse_fiscale(self):
        result = classify_doc_category(
            "liasse fiscale 2058 résultat fiscal impôt sur les sociétés", "liasse.pdf"
        )
        assert result == "liasse_fiscale"

    def test_grand_livre(self):
        result = classify_doc_category("grand livre écriture comptable balance lettrage", "gl.pdf")
        assert result == "grand_livre"

    def test_contrat(self):
        result = classify_doc_category(
            "contrat de bail clause article signataires les parties", "contrat.pdf"
        )
        assert result == "contrat"

    def test_facture(self):
        result = classify_doc_category(
            "facture total ttc tva règlement bon de commande", "facture.pdf"
        )
        assert result == "facture"

    def test_default_autre(self):
        result = classify_doc_category("document quelconque", "doc.pdf")
        assert result == "autre"


class TestSuggestClient:
    def test_societe(self):
        dets = [{"entity_type": "SOCIETE", "value_excerpt": "DUPONT CONSEIL SAS"}]
        assert suggest_client("", dets) == "DUPONT CONSEIL SAS"

    def test_company(self):
        dets = [{"entity_type": "COMPANY", "value_excerpt": "MARTIN SA"}]
        assert suggest_client("", dets) == "MARTIN SA"

    def test_person_fallback(self):
        dets = [{"entity_type": "PERSON", "value_excerpt": "Jean Dupont"}]
        assert suggest_client("", dets) == "Jean Dupont"

    def test_none_when_empty(self):
        assert suggest_client("", []) is None

    def test_short_value_ignored(self):
        dets = [{"entity_type": "SOCIETE", "value_excerpt": "AB"}]
        assert suggest_client("", dets) is None


class TestBuildMetadataSuggestions:
    def test_returns_all_keys(self):
        result = build_metadata_suggestions(
            text="bilan actif passif capitaux propres exercice 2024",
            filename="bilan_2024.pdf",
            detections=[{"entity_type": "SOCIETE", "value_excerpt": "DUPONT SAS"}],
        )
        assert "doc_category" in result
        assert "exercice" in result
        assert "client_suggestion" in result
        assert result["exercice"] == "2024"
        assert result["doc_category"] == "bilan"
        assert result["client_suggestion"] == "DUPONT SAS"
