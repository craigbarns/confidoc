"""B2B anonymization non-regression tests for sensitive French documents."""

from app.core.tokens import (
    TOKEN_ADRESSE,
    TOKEN_EMAIL,
    TOKEN_IBAN,
    TOKEN_PERSONNE,
    TOKEN_SIRET,
    TOKEN_SOCIETE,
    TOKEN_TELEPHONE,
)
from app.services.anonymization_service import anonymize_text


def test_strict_profile_masks_direct_and_quasi_identifiers():
    text = (
        "Client: SCI RIVIERA PATRIMOINE\n"
        "Gerante: Mme Claire Moreau\n"
        "Email: claire.moreau@example.fr\n"
        "Telephone: 06 12 34 56 78\n"
        "IBAN: FR76 3000 6000 0112 3456 7890 189\n"
        "SIRET: 123 456 789 01234\n"
        "Adresse: 12 avenue Victor Hugo 75016 Paris\n"
        "Nee le 14/02/1981 a Marseille\n"
    )

    out, detections, _ = anonymize_text(
        text,
        profile="strict",
        document_type="accounting",
    )

    for leak in (
        "Claire",
        "Moreau",
        "claire.moreau@example.fr",
        "06 12 34 56 78",
        "FR76 3000 6000 0112 3456 7890 189",
        "123 456 789 01234",
        "12 avenue Victor Hugo",
        "75016 Paris",
        "Marseille",
    ):
        assert leak not in out

    replacements = {item["replacement"] for item in detections}
    assert TOKEN_PERSONNE in replacements
    assert TOKEN_EMAIL in replacements
    assert TOKEN_TELEPHONE in replacements
    assert TOKEN_IBAN in replacements
    assert TOKEN_SIRET in replacements
    assert TOKEN_ADRESSE in replacements


def test_dataset_accounting_pseudo_keeps_business_amounts_but_masks_identities():
    text = (
        "SAS DUPONT CONSEIL\n"
        "SIRET 832 419 428 00038\n"
        "M. Jean Dupont\n"
        "jean.dupont@dupont-conseil.fr\n"
        "Chiffre d'affaires 245 000,00 EUR\n"
        "Resultat net 31 500,00 EUR\n"
    )

    out, detections, _ = anonymize_text(
        text,
        profile="dataset_accounting_pseudo",
        document_type="accounting",
    )

    assert "245 000,00 EUR" in out
    assert "31 500,00 EUR" in out
    for leak in ("DUPONT CONSEIL", "832 419 428 00038", "Jean Dupont", "jean.dupont"):
        assert leak not in out

    replacements = {item["replacement"] for item in detections}
    assert any(rep.startswith("[SOCIETE") for rep in replacements) or TOKEN_SOCIETE in replacements
    assert (
        any(rep.startswith("[PERSONNE") for rep in replacements)
        or TOKEN_PERSONNE in replacements
    )
