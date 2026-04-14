"""Tests for app.core.tokens — centralized PII token constants.

Vérifie :
- Tous les tokens sont des strings non vides au format [MAJUSCULES]
- Le SEMANTIC_MAP couvre les alias anglais ET français
- Les tokens sont uniques (pas de valeur dupliquée accidentelle)
- Import sans side effects
"""

from __future__ import annotations

import re

import pytest

from app.core import tokens as T


# ── Constants format ──────────────────────────────────────────────────

EXPECTED_TOKENS = [
    ("TOKEN_PERSONNE", T.TOKEN_PERSONNE),
    ("TOKEN_EMAIL", T.TOKEN_EMAIL),
    ("TOKEN_TELEPHONE", T.TOKEN_TELEPHONE),
    ("TOKEN_ADRESSE", T.TOKEN_ADRESSE),
    ("TOKEN_VILLE", T.TOKEN_VILLE),
    ("TOKEN_IBAN", T.TOKEN_IBAN),
    ("TOKEN_SIRET", T.TOKEN_SIRET),
    ("TOKEN_SIREN", T.TOKEN_SIREN),
    ("TOKEN_TVA", T.TOKEN_TVA),
    ("TOKEN_NSS", T.TOKEN_NSS),
    ("TOKEN_DATE", T.TOKEN_DATE),
    ("TOKEN_DATE_NAISSANCE", T.TOKEN_DATE_NAISSANCE),
    ("TOKEN_MONTANT", T.TOKEN_MONTANT),
    ("TOKEN_REF_FACTURE", T.TOKEN_REF_FACTURE),
    ("TOKEN_SOCIETE", T.TOKEN_SOCIETE),
    ("TOKEN_EMPRUNT", T.TOKEN_EMPRUNT),
    ("TOKEN_CADASTRE", T.TOKEN_CADASTRE),
    ("TOKEN_NAISSANCE", T.TOKEN_NAISSANCE),
    ("TOKEN_ID", T.TOKEN_ID),
    ("TOKEN_REDACTED", T.TOKEN_REDACTED),
]

TOKEN_PATTERN = re.compile(r"^\[[A-Z_]+\]$")


class TestTokenFormat:
    @pytest.mark.parametrize("name,value", EXPECTED_TOKENS)
    def test_token_is_bracketed_uppercase(self, name: str, value: str):
        assert TOKEN_PATTERN.match(value), (
            f"{name} = {value!r} doit être au format [MAJUSCULES]"
        )

    @pytest.mark.parametrize("name,value", EXPECTED_TOKENS)
    def test_token_is_non_empty(self, name: str, value: str):
        assert value.strip("[]"), f"{name} ne doit pas être vide"

    def test_all_token_values_are_unique(self):
        values = [v for _, v in EXPECTED_TOKENS]
        assert len(values) == len(set(values)), "Des tokens ont des valeurs dupliquées"


class TestSemanticMap:
    """Le SEMANTIC_MAP doit couvrir les alias courants."""

    def test_map_is_non_empty(self):
        assert len(T.SEMANTIC_MAP) > 10

    def test_person_aliases(self):
        assert "PERSONNE" in T.SEMANTIC_MAP
        assert "PERSON" in T.SEMANTIC_MAP
        assert T.SEMANTIC_MAP["PERSONNE"] == T.TOKEN_PERSONNE
        assert T.SEMANTIC_MAP["PERSON"] == T.TOKEN_PERSONNE

    def test_phone_aliases(self):
        assert "TELEPHONE" in T.SEMANTIC_MAP
        assert "PHONE" in T.SEMANTIC_MAP
        assert T.SEMANTIC_MAP["PHONE"] == T.TOKEN_TELEPHONE

    def test_company_id_aliases(self):
        assert "SIRET" in T.SEMANTIC_MAP
        assert "SIREN" in T.SEMANTIC_MAP
        assert "TVA" in T.SEMANTIC_MAP
        assert "VAT" in T.SEMANTIC_MAP
        assert T.SEMANTIC_MAP["VAT"] == T.TOKEN_TVA

    def test_address_aliases(self):
        assert "ADRESSE" in T.SEMANTIC_MAP
        assert "ADDRESS" in T.SEMANTIC_MAP
        assert T.SEMANTIC_MAP["ADDRESS"] == T.TOKEN_ADRESSE

    def test_amount_aliases(self):
        assert "MONTANT" in T.SEMANTIC_MAP
        assert "AMOUNT" in T.SEMANTIC_MAP
        assert T.SEMANTIC_MAP["AMOUNT"] == T.TOKEN_MONTANT

    def test_invoice_aliases(self):
        assert "REF_FACTURE" in T.SEMANTIC_MAP
        assert "INVOICE_REF" in T.SEMANTIC_MAP

    def test_all_values_are_known_tokens(self):
        known_values = {v for _, v in EXPECTED_TOKENS}
        for key, val in T.SEMANTIC_MAP.items():
            assert val in known_values, (
                f"SEMANTIC_MAP[{key!r}] = {val!r} n'est pas un TOKEN_* connu"
            )
