"""Tests unitaires extracteur releve_bancaire (MVP)."""

from app.services.structured_dataset_service import build_structured_dataset


def test_releve_bancaire_core_ready_on_balanced_statement():
    text = """
    RELEVE BANCAIRE
    Banque: BNP PARIBAS
    Titulaire: CABINET ALPHA EXPERTISE
    Periode du 01/01/2025 au 31/01/2025
    Solde initial 1 000,00
    02/01/2025 VIREMENT CLIENT X 0,00 1 200,00
    08/01/2025 PRELEVEMENT LOYER 500,00 0,00
    14/01/2025 FRAIS BANCAIRES 20,00 0,00
    Nouveau solde 1 680,00
    """
    out = build_structured_dataset(
        anonymized_text=text,
        extraction_text=text,
        requested_doc_type="releve_bancaire",
        original_filename="releve_janvier.pdf",
    )
    assert out["doc_type"] == "releve_bancaire"
    assert out["provenance"]["extractor_name"] == "extractor_releve_bancaire"
    assert out["fields"]["solde_initial"]["value"] == 1000.0
    assert out["fields"]["solde_final"]["value"] == 1680.0
    assert out["quality"]["ready_for_ai_core"] is True
    assert out["quality"]["ready_for_ai"] is True
    assert out["quality"]["balance_gap"] == 0.0
    assert out["quality"]["operations_parsed_count"] >= 3
    assert "balance_mismatch" not in out["quality"]["quality_flags"]


def test_releve_bancaire_flags_balance_mismatch():
    text = """
    RELEVE BANCAIRE
    Banque: LCL
    Periode du 01/02/2025 au 28/02/2025
    Solde initial 1 000,00
    02/02/2025 VIREMENT CLIENT 0,00 500,00
    10/02/2025 PAIEMENT CB 300,00 0,00
    Solde final 3 000,00
    """
    out = build_structured_dataset(
        anonymized_text=text,
        extraction_text=text,
        requested_doc_type="releve_bancaire",
        original_filename="releve_fevrier.pdf",
    )
    assert out["quality"]["ready_for_ai_core"] is False
    assert out["quality"]["ready_for_ai"] is False
    assert "balance_mismatch" in out["quality"]["quality_flags"]
