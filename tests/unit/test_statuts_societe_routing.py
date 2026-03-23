"""Tests de routage/statut pour les statuts de société."""

from app.services.structured_dataset_service import build_structured_dataset


def test_statuts_societe_is_detected_and_flagged_as_not_supported_yet():
    text = """
    STATUTS
    Forme juridique : Société à responsabilité limitée
    Dénomination : RENOV EAU PLOMBERIE EURL
    Siège social : Marseille
    Capital social : 5 000 euros
    Objet social : plomberie générale
    Durée : 99 ans
    Immatriculée au RCS Marseille
    """
    out = build_structured_dataset(
        anonymized_text=text,
        extraction_text=text,
        requested_doc_type="auto",
        original_filename="RENOV_EAU_PLOMBERIE_EURL.pdf",
    )
    assert out["doc_type"] == "statuts_societe"
    assert out["provenance"]["extractor_name"] == "extractor_statuts_societe_stub"
    flags = set(out["quality"]["quality_flags"] or [])
    assert "doc_type_not_supported_yet" in flags
    assert out["quality"]["ready_for_ai"] is False
