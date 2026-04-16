import pytest
import os
import json
from app.services.dictionary_anonymization_service import (
    anonymize_with_dictionary,
    anonymize_document_dictionary,
    _normalize_ocr_identifiers,
    _count_occurrences,
    _load_external_rules
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
    text = "Mon nom est GREGORY BARANES, je travaille chez WEMADE à MARSEILLE avec WEBUILD. Email: test@test.com"
    res = anonymize_with_dictionary(text)
    
    anonymized = res["anonymized_text"]
    assert "[PERSONNE_1]" in anonymized
    assert "[SOCIETE_1]" in anonymized
    assert "[VILLE]" in anonymized
    assert "[SOCIETE_LIEE_1]" in anonymized
    assert "[EMAIL]" in anonymized
    
    # Should contain registry
    registry = res["registry"]
    assert registry is not None

def test_anonymize_with_dictionary_partial_and_post_cleanup():
    # Account 421 BARANES
    text = "Client 421 BARANES is here. Siret 83241942812345. 41 RUE FONGATE\n13006 MARSEILLE"
    res = anonymize_with_dictionary(text)
    
    anonymized = res["anonymized_text"]
    assert "421 [PERSONNE_1]" in anonymized
    assert "[ADRESSE_SOCIETE_1]" in anonymized

@pytest.mark.asyncio
async def test_anonymize_document_dictionary():
    # 354-355
    text = "Mon adresse est 91 RUE BRETEUIL\n13006 MARSEILLE."
    text_anon, entities, registry = await anonymize_document_dictionary(text)
    assert "[ADRESSE_CABINET_1]" in text_anon
    assert isinstance(entities, list)
    assert registry is not None
