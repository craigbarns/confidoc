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


def test_bilan_flattened_multicolumn_prefers_net_total_column() -> None:
    text = """
    ---PAGE 4---
    Exprimé en €
    Rubriques
    ACTIF IMMOBILISE
    ACTIF CIRCULANT
    TOTAL GENERAL
    Montant Brut
    262 433 156
    77 754 903
    340 188 058
    Amort. Prov.
    179 127 950
    21 613 465
    200 741 415
    31/12/2024
    83 305 206
    56 141 438
    139 446 644
    31/12/2023
    89 453 790
    95 438 152
    184 891 942
    Bilan - Actif
    ---PAGE 5---
    CAPITAUX PROPRES
    DETTES
    TOTAL GENERAL
    31/12/2024
    141 656
    136 972 264
    139 446 644
    31/12/2023
    22 960 871
    154 639 149
    184 891 942
    Bilan - Passif
    """
    fields = _extract_bilan(text)
    assert fields["total_actif"]["value"] == 139_446_644.0
    assert fields["total_passif"]["value"] == 139_446_644.0
    assert fields["total_actif_n1"]["value"] == 184_891_942.0
    assert fields["total_actif"]["source_hint"] == "fallback:flattened_multicolumn_actif_net_column"
