"""Tests du pipeline d'anonymisation regex (cœur du moteur PII).

Couvre :
- Détection emails, téléphones FR/intl, IBAN, SIRET, SIREN, NSS, TVA
- Détection noms avec titre (Monsieur / Mme / Dr / Me)
- Détection adresses et villes (code postal)
- Faux positifs filtrés
- anonymize_text end-to-end
- clean_ocr_artifacts
- classify_document_type
- Profils : moderate vs strict
- Préservation des indices (pas de décalage après remplacement)
"""

from __future__ import annotations

import pytest

from app.services.anonymization_service import (
    _detect_entities,
    _is_false_positive,
    anonymize_text,
    clean_ocr_artifacts,
    classify_document_type,
)
from app.core.tokens import (
    TOKEN_EMAIL, TOKEN_TELEPHONE, TOKEN_IBAN, TOKEN_SIRET, TOKEN_SIREN,
    TOKEN_TVA, TOKEN_NSS, TOKEN_ADRESSE, TOKEN_VILLE, TOKEN_PERSONNE,
    TOKEN_MONTANT, TOKEN_REDACTED,
)


# ── Helpers ───────────────────────────────────────────────────────────

def _find_replacements(detections: list[dict], entity_type: str) -> list[str]:
    return [d["replacement"] for d in detections if d["entity_type"] == entity_type]


def _find_excerpts(detections: list[dict], entity_type: str) -> list[str]:
    return [d["value_excerpt"] for d in detections if d["entity_type"] == entity_type]


# ══════════════════════════════════════════════════════════════════════
# EMAIL
# ══════════════════════════════════════════════════════════════════════

class TestEmailDetection:
    def test_simple_email(self):
        text = "Contactez jean.dupont@example.com pour info."
        dets = _detect_entities(text)
        reps = _find_replacements(dets, "email")
        assert reps == [TOKEN_EMAIL]

    def test_email_with_plus(self):
        text = "user+tag@domain.org est mon adresse."
        dets = _detect_entities(text)
        assert any(d["entity_type"] == "email" for d in dets)

    def test_multiple_emails(self):
        text = "alice@corp.fr et bob@corp.fr sont en copie."
        dets = _detect_entities(text)
        emails = [d for d in dets if d["entity_type"] == "email"]
        assert len(emails) == 2

    def test_no_email_false_positive(self):
        text = "Le document concerne le dossier n°1234."
        dets = _detect_entities(text)
        assert not any(d["entity_type"] == "email" for d in dets)


# ══════════════════════════════════════════════════════════════════════
# TÉLÉPHONE
# ══════════════════════════════════════════════════════════════════════

class TestPhoneDetection:
    def test_french_mobile(self):
        text = "Appelez le 06 12 34 56 78 pour confirmation."
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_TELEPHONE for d in dets)

    def test_french_landline(self):
        text = "Notre standard : 01.23.45.67.89"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_TELEPHONE for d in dets)

    def test_french_with_plus33(self):
        text = "Numéro international : +33 6 12 34 56 78"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_TELEPHONE for d in dets)

    def test_international_phone(self):
        text = "Appelez le +1-800-555-0199 depuis les USA."
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_TELEPHONE for d in dets)


# ══════════════════════════════════════════════════════════════════════
# IBAN
# ══════════════════════════════════════════════════════════════════════

class TestIBANDetection:
    def test_french_iban_spaced(self):
        text = "IBAN : FR76 3000 6000 0112 3456 7890 189"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_IBAN for d in dets)

    def test_french_iban_compact(self):
        text = "Virements vers FR7630006000011234567890189"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_IBAN for d in dets)

    def test_no_iban_for_short_number(self):
        text = "Numéro dossier : 1234567890"
        dets = _detect_entities(text)
        iban_dets = [d for d in dets if d["replacement"] == TOKEN_IBAN]
        # 10-digit number should not be detected as IBAN
        for d in iban_dets:
            assert len(d["value_excerpt"].replace(" ", "")) >= 14


# ══════════════════════════════════════════════════════════════════════
# SIRET / SIREN / TVA
# ══════════════════════════════════════════════════════════════════════

class TestCompanyIdentifiers:
    def test_siret_detection(self):
        text = "SIRET : 123 456 789 01234"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_SIRET for d in dets)

    def test_siren_detection(self):
        text = "SIREN : 123 456 789"
        dets = _detect_entities(text)
        # SIREN pattern may match
        assert any(d["replacement"] in (TOKEN_SIREN, TOKEN_SIRET) for d in dets)

    def test_tva_detection(self):
        text = "TVA intracommunautaire FR 12 345 678 901"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_TVA for d in dets)


# ══════════════════════════════════════════════════════════════════════
# NSS
# ══════════════════════════════════════════════════════════════════════

class TestNSSDetection:
    def test_nss_male(self):
        # Format: 1 + YY + MM + dept(2) + commune(3) + order(3) + key(2)
        text = "N° SS : 1 85 02 75 023 456 78"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_NSS for d in dets)

    def test_nss_female(self):
        text = "Assuré : 2 95 11 69 001 234 56"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_NSS for d in dets)


# ══════════════════════════════════════════════════════════════════════
# PERSONNES (noms avec titre)
# ══════════════════════════════════════════════════════════════════════

class TestPersonDetection:
    def test_monsieur(self):
        text = "Bonjour Monsieur Jean Dupont, votre dossier est prêt."
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_PERSONNE for d in dets)

    def test_madame(self):
        text = "Destinataire : Mme Marie Martin"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_PERSONNE for d in dets)

    def test_docteur(self):
        text = "Prescrit par Dr. Pierre Bernard."
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_PERSONNE for d in dets)

    def test_maitre(self):
        text = "Me Sophie Lefebvre, avocate au barreau de Paris."
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_PERSONNE for d in dets)


# ══════════════════════════════════════════════════════════════════════
# ADRESSES & VILLES
# ══════════════════════════════════════════════════════════════════════

class TestAddressDetection:
    def test_street_address(self):
        text = "Domicile : 12 rue des Lilas, appartement 4"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_ADRESSE for d in dets)

    def test_avenue(self):
        text = "Adresse : 45 avenue de la République"
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_ADRESSE for d in dets)

    def test_postal_code_city(self):
        text = "Domicile sis au 75008 Paris."
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_VILLE for d in dets)

    def test_postal_code_complex_city(self):
        text = "69001 Lyon est la ville concernée."
        dets = _detect_entities(text)
        assert any(d["replacement"] == TOKEN_VILLE for d in dets)


# ══════════════════════════════════════════════════════════════════════
# FAUX POSITIFS
# ══════════════════════════════════════════════════════════════════════

class TestFalsePositives:
    @pytest.mark.parametrize("word", [
        "FACTURE", "TOTAL", "TVA", "SOLDE", "DATE", "CLIENT",
        "DEBIT", "CREDIT", "BILAN", "ACTIF", "PASSIF",
    ])
    def test_accounting_header_not_flagged(self, word: str):
        assert _is_false_positive(word) is True

    def test_mixed_case_false_positive(self):
        assert _is_false_positive("Facture") is True

    def test_real_name_not_false_positive(self):
        assert _is_false_positive("Jean") is False

    def test_random_word_not_false_positive(self):
        assert _is_false_positive("contrat") is False


# ══════════════════════════════════════════════════════════════════════
# anonymize_text — end-to-end
# ══════════════════════════════════════════════════════════════════════

class TestAnonymizeText:
    def test_empty_text_returns_unchanged(self):
        out, dets, reg = anonymize_text("")
        assert out == ""
        assert dets == []

    def test_whitespace_only_returns_unchanged(self):
        out, dets, reg = anonymize_text("   \n  ")
        assert out.strip() == ""

    def test_email_replaced_in_output(self):
        text = "Envoyez un mail à alice@example.com maintenant."
        out, dets, _ = anonymize_text(text)
        assert "alice@example.com" not in out
        assert TOKEN_EMAIL in out

    def test_phone_replaced_in_output(self):
        text = "Rappeler le 06 12 34 56 78 dès que possible."
        out, dets, _ = anonymize_text(text)
        assert "06 12 34 56 78" not in out
        assert TOKEN_TELEPHONE in out

    def test_multiple_entities_all_replaced(self):
        text = (
            "Contact : Mme Dupont alice@example.com 06 12 34 56 78 "
            "domiciliée au 12 rue des Pins 75001 Paris"
        )
        out, dets, _ = anonymize_text(text)
        assert "alice@example.com" not in out
        assert "06 12 34 56 78" not in out

    def test_no_pii_text_unchanged(self):
        text = "Le solde de votre compte est conforme à notre comptabilité."
        out, dets, _ = anonymize_text(text)
        # Should not have many detections on pure accounting text
        assert "solde" in out.lower()

    def test_detections_indices_valid(self):
        text = "Contact : alice@example.com pour info."
        out, dets, _ = anonymize_text(text)
        for d in dets:
            assert d["start_index"] >= 0
            assert d["end_index"] > d["start_index"]
            assert d["end_index"] <= len(text)

    def test_returns_entity_registry(self):
        from app.services.entity_registry import EntityRegistry
        text = "Mme Dupont alice@example.com"
        out, dets, registry = anonymize_text(text)
        assert isinstance(registry, EntityRegistry)

    def test_strict_profile_detects_more(self):
        text = "Jean est né le 01/01/1985 à Lyon."
        _, dets_moderate, _ = anonymize_text(text, profile="moderate")
        _, dets_strict, _ = anonymize_text(text, profile="strict")
        # Strict should have >= detections than moderate
        assert len(dets_strict) >= len(dets_moderate)

    def test_text_without_pii_has_no_detections(self):
        text = "Exercice comptable clos au 31 décembre 2023."
        _, dets, _ = anonymize_text(text)
        # Ensure no person/email/phone detected
        pii_types = {"email", "phone_fr", "phone_intl", "person_title"}
        pii_dets = [d for d in dets if d["entity_type"] in pii_types]
        assert len(pii_dets) == 0


# ══════════════════════════════════════════════════════════════════════
# clean_ocr_artifacts
# ══════════════════════════════════════════════════════════════════════

class TestCleanOCRArtifacts:
    def test_broken_token_trailing_chars_removed(self):
        text = "[PERSONNE]ÉE some text"
        result = clean_ocr_artifacts(text)
        assert result.startswith("[PERSONNE]")
        assert "É" not in result or result.index("É") > result.index("]")

    def test_duplicate_adjacent_tokens_deduplicated(self):
        text = "[PERSONNE_1] [PERSONNE_1] doit être payé."
        result = clean_ocr_artifacts(text)
        assert result.count("[PERSONNE_1]") == 1

    def test_excessive_blank_lines_collapsed(self):
        text = "ligne 1\n\n\n\n\n\nligne 2"
        result = clean_ocr_artifacts(text)
        assert "\n\n\n\n" not in result

    def test_clean_empty_returns_empty(self):
        assert clean_ocr_artifacts("") == ""

    def test_clean_normal_text_unchanged(self):
        text = "Le solde est de 1 234,00 EUR."
        result = clean_ocr_artifacts(text)
        assert "solde" in result

    def test_orphan_closing_bracket_removed(self):
        text = "[EMAIL]] reste du texte"
        result = clean_ocr_artifacts(text)
        assert "]]" not in result


# ══════════════════════════════════════════════════════════════════════
# classify_document_type
# ══════════════════════════════════════════════════════════════════════

class TestClassifyDocumentType:
    def test_invoice_detection(self):
        text = "FACTURE N°2024-001 - Total TTC : 1 200,00 EUR TVA 20%"
        assert classify_document_type(text) == "invoice"

    def test_invoice_from_filename(self):
        assert classify_document_type("texte générique", filename="facture_2024.pdf") == "invoice"

    def test_accounting_detection(self):
        text = "Grand livre général - Journal des écritures comptables"
        assert classify_document_type(text) == "accounting"

    def test_legal_detection(self):
        text = "Le présent contrat est conclu entre les parties en vertu des clauses suivantes."
        assert classify_document_type(text) == "legal"

    def test_legal_tribunal(self):
        text = "Assignation devant le tribunal judiciaire de Paris"
        assert classify_document_type(text) == "legal"

    def test_generic_fallback(self):
        text = "Document sans indice de type particulier."
        assert classify_document_type(text) == "generic"

    def test_invoice_priority_over_legal(self):
        text = "Facture pour prestations juridiques - Total TTC 500 EUR"
        # Invoice hints should take priority
        result = classify_document_type(text)
        assert result == "invoice"
