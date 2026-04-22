import json

import pytest

from app.services.dictionary_anonymization_service import (
    anonymize_document_dictionary,
    anonymize_with_dictionary,
)


def test_anonymize_with_dictionary_empty():
    # 232-338 coverage partially here
    res = anonymize_with_dictionary("")
    assert res["anonymized_text"] == ""
    assert res["count"] == 0
    assert res["method"] == "dictionary"

def test_anonymize_with_dictionary_matches():
    text = (
        "Mon nom est Mme Alice Dupont, je travaille chez SAS ACME CONSEIL, "
        "12 rue Exemple 75008 Paris. Email: test@test.com"
    )
    res = anonymize_with_dictionary(text)

    anonymized = res["anonymized_text"]
    assert "[PERSONNE" in anonymized
    assert "[ADRESSE" in anonymized

    # Should contain registry
    registry = res["registry"]
    assert registry is not None

def test_anonymize_with_dictionary_partial_and_post_cleanup():
    text = "Client 421 DUPONT is here. Siret 83241942812345. 41 RUE EXEMPLE\n75008 PARIS"
    res = anonymize_with_dictionary(text)

    anonymized = res["anonymized_text"]
    assert "[COMPTE" in anonymized
    assert "[ADRESSE" in anonymized

def test_anonymize_with_dictionary_masks_labeled_identity_fields():
    text = (
        "Nom: Gregory Baranes\n"
        "Prénom: Gregory\n"
        "Raison sociale: ConfiDoc SAS\n"
        "N° client: C2024-001\n"
        "BIC: SOGEFRPP\n"
        "Date de naissance: 01/01/1985 à Lyon"
    )
    res = anonymize_with_dictionary(text)

    anonymized = res["anonymized_text"]
    assert "Gregory" not in anonymized
    assert "Baranes" not in anonymized
    assert "ConfiDoc" not in anonymized
    assert "C2024-001" not in anonymized
    assert "SOGEFRPP" not in anonymized
    assert "01/01/1985" not in anonymized
    assert "Lyon" not in anonymized
    assert "Nom: [DONNEE" in anonymized

def test_anonymize_with_dictionary_preserves_siret_and_vat_boundaries():
    text = (
        "Client: Alice Dupont\n"
        "Société: ACME Conseil SAS\n"
        "SIRET: 832 419 428 00038\n"
        "TVA: FR 12 832419428\n"
        "IBAN: FR76 3000 6000 0112 3456 7890 189\n"
        "Adresse: 12 rue Exemple 75008 Paris\n"
        "Téléphone: 06 12 34 56 78\n"
        "Email: alice.dupont@example.com"
    )
    res = anonymize_with_dictionary(text)

    anonymized = res["anonymized_text"]
    assert "Alice" not in anonymized
    assert "Dupont" not in anonymized
    assert "ACME" not in anonymized
    assert "832 419 428 00038" not in anonymized
    assert "FR 12 832419428" not in anonymized
    assert "FR76 3000 6000 0112 3456 7890 189" not in anonymized
    assert "06 12 34 56 78" not in anonymized
    assert "alice.dupont@example.com" not in anonymized
    assert "SIRET: [COMPTE" in anonymized
    assert "TVA: [COMPTE" in anonymized
    assert "IBAN: [BANQUE" in anonymized

def test_anonymize_with_dictionary_masks_accounting_name_lines_without_amount_false_positive():
    text = (
        "DUPONT ALICE\n"
        "421 DUPONT ALICE\n"
        "51210000 QONTO\n"
        "COMPTE DE RESULTAT\n"
        "CHIFFRE D AFFAIRES 120000 EUR\n"
        "RESULTAT NET 45000 EUR"
    )
    res = anonymize_with_dictionary(text)
    anonymized = res["anonymized_text"]
    assert "120000 EUR" in anonymized

@pytest.mark.asyncio
async def test_anonymize_document_dictionary():
    # 354-355
    text = "Mon adresse est 91 RUE EXEMPLE\n75008 PARIS."
    text_anon, entities, registry = await anonymize_document_dictionary(text)
    assert "[ADRESSE" in text_anon
    assert isinstance(entities, list)
    assert registry is not None
