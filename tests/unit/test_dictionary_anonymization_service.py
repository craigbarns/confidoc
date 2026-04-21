import json

import pytest

from app.services.dictionary_anonymization_service import (
    _count_occurrences,
    _load_external_rules,
    _normalize_ocr_identifiers,
    anonymize_document_dictionary,
    anonymize_with_dictionary,
)


def test_normalize_ocr_identifiers():
    # 192-202
    text = "Siret 832419428 in OCR is often 8324I942B or 8324l942B or O32419428 or S32419428"
    normalized = _normalize_ocr_identifiers(text)
    # the function mainly normalizes within long runs
    assert "832419428" in normalized

    # Let's test a very long alphanumeric block directly
    assert _normalize_ocr_identifiers("8324I942B011") == "832419428011"
    assert _normalize_ocr_identifiers("OIlSB12345O") == "01158123450"

def test_count_occurrences():
    # 207-208
    text = "hello Hello HELLO"
    assert _count_occurrences("hello", text, False) == 3
    assert _count_occurrences("hello", text, True) == 1

def test_load_external_rules(tmp_path, monkeypatch):
    # 31-36
    file_path = tmp_path / "rules.json"
    rules = {
        "replacement_rules": [["(?i)fake_rule", "[FAKE]", False]],
        "partial_replacements": [["(?i)fake_partial", "123 [FAKE]", False]],
        "post_cleanup_rules": [["(?i)fake_cleanup", "[FAKE_CLEAN]", False]]
    }
    file_path.write_text(json.dumps(rules), encoding="utf-8")

    monkeypatch.setenv("ANONYMIZATION_RULES_PATH", str(file_path))
    ret = _load_external_rules()
    assert ret is not None
    assert ret[0] == rules["replacement_rules"]

    # test error block
    monkeypatch.setenv("ANONYMIZATION_RULES_PATH", str(tmp_path / "does_not_exist.json"))
    ret2 = _load_external_rules()
    assert ret2 is None

    # test empty
    monkeypatch.setenv("ANONYMIZATION_RULES_PATH", "")
    ret3 = _load_external_rules()
    assert ret3 is None

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
    assert "[PERSONNE]" in anonymized
    assert "[SOCIETE]" in anonymized
    assert "[ADRESSE]" in anonymized
    assert "[EMAIL]" in anonymized

    # Should contain registry
    registry = res["registry"]
    assert registry is not None

def test_anonymize_with_dictionary_partial_and_post_cleanup():
    text = "Client 421 DUPONT is here. Siret 83241942812345. 41 RUE EXEMPLE\n75008 PARIS"
    res = anonymize_with_dictionary(text)

    anonymized = res["anonymized_text"]
    assert "421 [PERSONNE]" in anonymized
    assert "[ADRESSE]" in anonymized

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
    assert "Nom: [PERSONNE]" in anonymized
    assert "Raison sociale: [SOCIETE]" in anonymized
    assert "N° client: [ID]" in anonymized
    assert "BIC: [BIC]" in anonymized
    assert "Date de naissance: [DATE_NAISSANCE] à [VILLE]" in anonymized

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
    assert "SIRET: [SIRET]" in anonymized
    assert "TVA: [TVA]" in anonymized
    assert "IBAN: [IBAN]" in anonymized

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
    assert "DUPONT" not in anonymized
    assert "ALICE" not in anonymized
    assert "QONTO" not in anonymized
    assert "[PERSONNE]" in anonymized
    assert "421 [PERSONNE]" in anonymized
    assert "512 [BANQUE]" in anonymized
    assert "120000 EUR" in anonymized
    assert "45000 EUR" in anonymized
    assert "[ADRESSE_VILLE]" not in anonymized

@pytest.mark.asyncio
async def test_anonymize_document_dictionary():
    # 354-355
    text = "Mon adresse est 91 RUE EXEMPLE\n75008 PARIS."
    text_anon, entities, registry = await anonymize_document_dictionary(text)
    assert "[ADRESSE]" in text_anon
    assert isinstance(entities, list)
    assert registry is not None
