"""Tests de robustesse extraction (OCR bruité, garde-fous métier)."""

from app.services.structured_dataset_service import _extract_bilan, _extract_common_fields


def test_bilan_rejects_account_code_like_debts():
    text = """
    BILAN
    Total actif 1 250 000
    Total passif 1 250 000
    Dettes financières 45510000
    Dettes fournisseurs 40100000
    Capitaux propres 300000
    """
    fields = _extract_bilan(text)
    assert fields["total_passif"]["value"] == 1_250_000.0
    # Guardrail: values looking like account-code leakage are rejected.
    assert fields["dettes_financieres"]["value"] is None
    assert fields["dettes_fournisseurs"]["value"] is None
    assert fields["dettes_financieres"]["review_required"] is True
    assert fields["dettes_fournisseurs"]["review_required"] is True


def test_common_fields_rejects_noisy_company_header():
    text = """
    Raison sociale : GENERALE_
    Exercice 2024
    """
    fields = _extract_common_fields(text)
    assert fields["societe"]["value"] is None
    assert fields["societe"]["review_required"] is True


def test_common_fields_accepts_real_company_label():
    text = """
    Dénomination : CABINET COMPTABLE ALPHA
    Exercice 2024
    """
    fields = _extract_common_fields(text)
    assert fields["societe"]["value"] == "CABINET COMPTABLE ALPHA"
    assert fields["societe"]["review_required"] is False


def test_common_fields_rejects_non_company_phrase():
    text = """
    Cette société a pour objet la rénovation.
    """
    fields = _extract_common_fields(text)
    assert fields["societe"]["value"] is None
    assert fields["societe"]["review_required"] is True
