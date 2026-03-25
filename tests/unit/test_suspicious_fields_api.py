"""Tests for suspicious_fields propagation in API responses."""

from __future__ import annotations

from app.api.v1.ai import _generate_quality_warning, _add_suspicious_fields_to_payload


class TestGenerateQualityWarning:
    def test_no_suspicious_fields_returns_none(self):
        quality = {"suspicious_fields": []}
        result = _generate_quality_warning(quality)
        assert result is None

    def test_single_suspicious_field(self):
        quality = {"suspicious_fields": ["resultat_exercice"]}
        result = _generate_quality_warning(quality)
        assert "1 champ" in result
        assert "resultat_exercice" in result

    def test_two_suspicious_fields(self):
        quality = {"suspicious_fields": ["resultat_exercice", "total_actif"]}
        result = _generate_quality_warning(quality)
        assert "2 champs" in result
        assert "resultat_exercice" in result
        assert "total_actif" in result

    def test_many_suspicious_fields_generic_message(self):
        quality = {"suspicious_fields": ["a", "b", "c", "d"]}
        result = _generate_quality_warning(quality)
        assert "4 champs" in result
        # Should not list all fields when > 3
        assert "doivent être vérifiés" in result

    def test_missing_suspicious_fields_key(self):
        quality = {}
        result = _generate_quality_warning(quality)
        assert result is None


class TestAddSuspiciousFieldsToPayload:
    def test_adds_uncertain_fields_when_present(self):
        payload = {"doc_type": "bilan", "fields": ["a", "b"]}
        quality = {"suspicious_fields": ["field1", "field2"]}
        
        result = _add_suspicious_fields_to_payload(payload, quality)
        
        assert result["uncertain_fields"] == ["field1", "field2"]
        assert "data_quality_notes" in result
        assert "Attention" in result["data_quality_notes"]
        assert "field1" in result["data_quality_notes"]

    def test_no_modification_when_no_suspicious_fields(self):
        payload = {"doc_type": "bilan", "fields": ["a", "b"]}
        quality = {"suspicious_fields": []}
        
        result = _add_suspicious_fields_to_payload(payload, quality)
        
        assert "uncertain_fields" not in result
        assert "data_quality_notes" not in result
        assert result == payload

    def test_preserves_original_payload(self):
        payload = {"doc_type": "bilan", "fields": ["a", "b"]}
        quality = {"suspicious_fields": ["field1"]}
        
        result = _add_suspicious_fields_to_payload(payload, quality)
        
        # Original payload should not be modified
        assert payload == {"doc_type": "bilan", "fields": ["a", "b"]}
        # Result should have new keys
        assert result["doc_type"] == "bilan"
        assert result["uncertain_fields"] == ["field1"]
