"""Tests des helpers partagés (app.api.v1._doc_shared).

Couvre :
- _normalize_client_name : normalisation unicode/casse/espaces
- _sha256_text : hash déterministe, None safe
- _infer_semantic_type : mapping token → type sémantique
- _detection_item_to_response : sérialisation vers DetectionResponse
"""

from __future__ import annotations

import pytest

from app.api.v1._doc_shared import (
    _detection_item_to_response,
    _infer_semantic_type,
    _normalize_client_name,
    _sha256_text,
)
from app.core.tokens import (
    TOKEN_ADRESSE,
    TOKEN_CADASTRE,
    TOKEN_EMAIL,
    TOKEN_EMPRUNT,
    TOKEN_IBAN,
    TOKEN_MONTANT,
    TOKEN_NSS,
    TOKEN_PERSONNE,
    TOKEN_REF_FACTURE,
    TOKEN_SIREN,
    TOKEN_SIRET,
    TOKEN_SOCIETE,
    TOKEN_TELEPHONE,
    TOKEN_TVA,
    TOKEN_VILLE,
)

# ══════════════════════════════════════════════════════════════════════
# _normalize_client_name
# ══════════════════════════════════════════════════════════════════════


class TestNormalizeClientName:
    def test_lowercases(self):
        assert _normalize_client_name("ACME Corp") == "acme corp"

    def test_strips_whitespace(self):
        assert _normalize_client_name("  hello  ") == "hello"

    def test_collapses_multiple_spaces(self):
        assert _normalize_client_name("a  b   c") == "a b c"

    def test_none_returns_empty(self):
        assert _normalize_client_name(None) == ""

    def test_empty_returns_empty(self):
        assert _normalize_client_name("") == ""

    def test_unicode_preserved(self):
        result = _normalize_client_name("Société Générale")
        assert "société" in result
        assert "générale" in result

    def test_newlines_collapsed(self):
        result = _normalize_client_name("foo\nbar")
        assert "\n" not in result


# ══════════════════════════════════════════════════════════════════════
# _sha256_text
# ══════════════════════════════════════════════════════════════════════


class TestSha256Text:
    def test_deterministic(self):
        assert _sha256_text("hello") == _sha256_text("hello")

    def test_different_inputs_give_different_hashes(self):
        assert _sha256_text("hello") != _sha256_text("world")

    def test_returns_64_char_hex(self):
        h = _sha256_text("test")
        assert h is not None
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_none_returns_none(self):
        assert _sha256_text(None) is None

    def test_empty_returns_none(self):
        assert _sha256_text("") is None


# ══════════════════════════════════════════════════════════════════════
# _infer_semantic_type
# ══════════════════════════════════════════════════════════════════════


class TestInferSemanticType:
    @pytest.mark.parametrize(
        "token,expected",
        [
            (TOKEN_PERSONNE, "PERSON"),
            (TOKEN_EMAIL, "EMAIL"),
            (TOKEN_TELEPHONE, "PHONE"),
            (TOKEN_ADRESSE, "ADDRESS"),
            (TOKEN_IBAN, "BANK"),
            (TOKEN_SIRET, "COMPANY_ID"),
            (TOKEN_SIREN, "COMPANY_ID"),
            (TOKEN_TVA, "COMPANY_ID"),
            (TOKEN_NSS, "SOCIAL_SECURITY"),
            (TOKEN_MONTANT, "AMOUNT"),
            (TOKEN_REF_FACTURE, "INVOICE_REF"),
            (TOKEN_SOCIETE, "COMPANY"),
            (TOKEN_EMPRUNT, "LOAN_REF"),
            (TOKEN_CADASTRE, "PROPERTY_REF"),
            (TOKEN_VILLE, "ADDRESS"),
        ],
    )
    def test_known_token_maps_correctly(self, token: str, expected: str):
        result = _infer_semantic_type(token)
        assert result == expected, f"{token} → expected {expected}, got {result}"

    def test_unknown_token_returns_other(self):
        result = _infer_semantic_type("[UNKNOWN_XYZ]")
        assert result == "OTHER"

    def test_numbered_token_person(self):
        # Entity registry can produce [PERSONNE_1], [PERSONNE_2], etc.
        result = _infer_semantic_type("[PERSONNE_1]")
        assert result == "PERSON"

    def test_numbered_token_company(self):
        result = _infer_semantic_type("[SOCIETE_3]")
        assert result == "COMPANY"

    def test_case_insensitive(self):
        # The function uppercases internally
        result = _infer_semantic_type("[personne]")
        assert result == "PERSON"

    def test_empty_string_returns_other(self):
        result = _infer_semantic_type("")
        assert result == "OTHER"

    def test_redacted_token(self):
        # [REDACTED] doesn't map to a specific type
        result = _infer_semantic_type("[REDACTED]")
        assert isinstance(result, str)


# ══════════════════════════════════════════════════════════════════════
# _detection_item_to_response
# ══════════════════════════════════════════════════════════════════════


class TestDetectionItemToResponse:
    def test_full_item(self):
        item = {
            "entity_type": "email",
            "start_index": 10,
            "end_index": 30,
            "replacement": "[EMAIL]",
            "confidence": 0.95,
            "value_excerpt": "user@example.com",
        }
        resp = _detection_item_to_response(item)
        assert resp.entity_type == "email"
        assert resp.start_index == 10
        assert resp.end_index == 30
        assert resp.replacement == "[EMAIL]"
        assert resp.confidence == 0.95
        assert resp.value_excerpt == "user@example.com"

    def test_missing_fields_use_defaults(self):
        resp = _detection_item_to_response({})
        assert resp.entity_type == "UNKNOWN"
        assert resp.start_index == 0
        assert resp.end_index == 0
        assert resp.replacement == ""
        assert resp.confidence == 0.0
        assert resp.value_excerpt == ""

    def test_partial_item(self):
        item = {"entity_type": "phone", "replacement": TOKEN_TELEPHONE}
        resp = _detection_item_to_response(item)
        assert resp.entity_type == "phone"
        assert resp.replacement == TOKEN_TELEPHONE
