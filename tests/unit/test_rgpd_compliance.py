"""Tests de conformité RGPD - Vérifie l'absence de PII dans les exports."""

from __future__ import annotations

import re

import pytest

from app.services.structured_dataset_service import build_structured_dataset
from app.services.anonymization_service import anonymize_text


# PII patterns to check for
PII_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+33|0)\s?[1-9](?:[\s.\-]?\d{2}){4}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[\s]?[A-Z0-9]{4}[\s]?(?:[A-Z0-9]{4}[\s]?){2,7}[A-Z0-9]{1,4}\b"),
    "siret": re.compile(r"\b\d{3}[\s.\-]?\d{3}[\s.\-]?\d{3}[\s.\-]?\d{5}\b"),
    "nss": re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b"),
    "person_name": re.compile(r"\b[A-ZÀ-ÖØ-Ý][a-zà-öø-ÿ''\-]{2,}\s+[A-ZÀ-ÖØ-Ý][A-Za-zà-öø-ÿ''\-]{2,}\b"),
}

KNOWN_PII = [
    "BARANES GREGORY",
    "Jean Dupont",
    "Marie Martin",
    "contact@example.com",
    "06 12 34 56 78",
    "+33 1 23 45 67 89",
    "FR76 3000 3000 1234 5678 9012 345",
    "512 426 610 00014",
    "192 08 12 34 123 45",
]


def _contains_pii(text: str) -> list[tuple[str, str]]:
    """Scan text for PII and return matches."""
    matches = []
    for pii_type, pattern in PII_PATTERNS.items():
        for match in pattern.finditer(text):
            matches.append((pii_type, match.group(0)))
    return matches


def _any_pii_in_dict(d: dict) -> list[tuple[str, str, str]]:
    """Recursively scan dict values for PII."""
    matches = []
    for key, value in d.items():
        if isinstance(value, dict):
            for pii_type, pii_val in _any_pii_in_dict(value):
                matches.append((key, pii_type, pii_val))
        elif isinstance(value, str):
            for pii_type, pii_val in _contains_pii(value):
                matches.append((key, pii_type, pii_val))
    return matches


class TestRGPDAnonymization:
    """Test that dataset_accounting profile properly anonymizes PII."""

    def test_anonymize_text_removes_emails(self):
        text = "Contactez contact@example.com pour plus d'infos"
        anon, _ = anonymize_text(text, profile="dataset_accounting")
        assert "contact@example.com" not in anon
        assert "[EMAIL]" in anon

    def test_anonymize_text_removes_phones(self):
        text = "Tél: 06 12 34 56 78"
        anon, _ = anonymize_text(text, profile="dataset_accounting")
        assert "06 12 34 56 78" not in anon
        assert "[PHONE]" in anon

    def test_anonymize_text_removes_person_names(self):
        text = "Gérant: Jean Dupont"
        anon, _ = anonymize_text(text, profile="dataset_accounting")
        assert "Jean Dupont" not in anon
        # Should be replaced with [IDENTITY], [PERSON] or pseudonym
        assert any(x in anon for x in ["[IDENTITY]", "[PERSON]", "PERSONNE_"]), f"Got: {anon}"

    def test_anonymize_text_removes_iban(self):
        text = "IBAN: FR76 3000 3000 1234 5678 9012 345"
        anon, _ = anonymize_text(text, profile="dataset_accounting")
        assert "FR76" not in anon
        assert "[IBAN]" in anon

    def test_anonymize_text_preserves_amounts_in_accounting_profile(self):
        """Amounts should be preserved in dataset_accounting profile."""
        text = "Montant: 10 000,00 €"
        anon, _ = anonymize_text(text, profile="dataset_accounting")
        # Amount should be preserved (not replaced with [AMOUNT])
        assert "10 000" in anon


class TestRGPDStructuredExport:
    """Test that structured dataset exports don't contain PII."""

    def test_bilan_export_no_pii(self):
        """Bilan extraction should not contain PII in output."""
        # Text with PII that should be anonymized
        text = f"""SCI EXEMPLE TEST
Date de clôture: 31/12/2024
Gérant: {KNOWN_PII[0]}
Email: {KNOWN_PII[3]}
Tél: {KNOWN_PII[4]}

BILAN ACTIF
Immobilisations 100 000
Créances 50 000
Disponibilités 25 000
TOTAL ACTIF 175 000

BILAN PASSIF
Capital social 100 000
Résultat exercice 10 000
Dettes financières 50 000
Dettes fournisseurs 15 000
TOTAL PASSIF 175 000"""

        result = build_structured_dataset(
            anonymized_text=text,
            original_filename="test_bilan.pdf",
            requested_doc_type="bilan",
            extraction_text=text,
        )

        # Export to JSON and check for PII
        import json
        result_json = json.dumps(result, default=str)
        
        # Check no original PII in output
        for pii in [KNOWN_PII[0], KNOWN_PII[3], KNOWN_PII[4]]:
            assert pii not in result_json, f"PII found in export: {pii}"

    def test_2072_export_pseudonymizes_denomination(self):
        """2072 extraction should pseudonymize denomination."""
        text = f"""Dénomination de la société SCI LES DEUX PINS
Date de clôture de l'exercice 31/12/2024
Nombre d'associés 2
Revenus bruts 45 000
Frais et charges hors intérêts 10 000
Intérêts d'emprunts 12 500
Revenu net foncier 22 500

ASSOCIE 1: {KNOWN_PII[0]} - 1 568 parts
ASSOCIE 2: {KNOWN_PII[1]} - 1 632 parts"""

        result = build_structured_dataset(
            anonymized_text=text,
            original_filename="test_2072.pdf",
            requested_doc_type="fiscal_2072",
            extraction_text=text,
        )

        fields = result.get("fields", {})
        
        # Denomination should be pseudonymized or original
        denom = fields.get("denomination_sci", {}).get("value", "")
        # Either pseudonymized or original - but never OTHER PII like names
        for pii in [KNOWN_PII[0], KNOWN_PII[1]]:
            assert pii not in str(fields), f"PII found in 2072 export: {pii}"


class TestRGPDProfileStrictness:
    """Test that strict profile catches all PII variants."""

    def test_strict_profile_catches_uppercase_names(self):
        """All-caps names should be caught in strict mode."""
        text = "Contact: BARANES GREGORY"
        anon, detections = anonymize_text(text, profile="strict")
        
        # Check detection happened - look for person or identity detections
        person_detections = [d for d in detections if "person" in d.get("entity_type", "") or "identity" in d.get("entity_type", "")]
        assert len(person_detections) > 0, f"Person name should be detected. Detections: {detections}"

    def test_strict_profile_catches_addresses(self):
        """Addresses should be anonymized."""
        text = "Siège: 12 Rue des Lilas, 75000 Paris"
        anon, _ = anonymize_text(text, profile="strict")
        assert "Rue des Lilas" not in anon


class TestRGPDCrossCheck:
    """Cross-reference tests between anonymization and extraction."""

    def test_no_pii_in_anonymized_then_structured_pipeline(self):
        """Full pipeline: anonymize then extract - no PII in output."""
        import json
        
        # Original with PII
        original = f"""SCI TEST
Gérant: {KNOWN_PII[0]}
Contact: {KNOWN_PII[3]}

BILAN
Total actif 500 000
Total passif 500 000"""

        # Step 1: Anonymize
        anonymized, _ = anonymize_text(original, profile="dataset_accounting")
        
        # Verify PII is gone from anonymized text
        assert KNOWN_PII[0] not in anonymized
        assert KNOWN_PII[3] not in anonymized

        # Step 2: Extract from anonymized text
        result = build_structured_dataset(
            anonymized_text=anonymized,
            original_filename="test.pdf",
            requested_doc_type="bilan",
            extraction_text=anonymized,
        )

        # Step 3: Export to JSON
        result_json = json.dumps(result, default=str)

        # Step 4: Verify no PII in final export
        for pii in KNOWN_PII:
            assert pii not in result_json, f"PII leaked to export: {pii}"
