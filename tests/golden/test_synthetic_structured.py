"""Golden léger : documents synthétiques (sans PDF) pour régression extracteurs."""

from __future__ import annotations

from app.services.structured_dataset_service import build_structured_dataset


def _bilan_like_text() -> str:
    return """
    Bilan — situation patrimoniale
    Total de l'actif 1 000 000
    Total du passif 1 000 000
    Capitaux propres 400 000
    Dettes financières 100 000
    Dettes fournisseurs 50 000
    Résultat de l'exercice 25 000
    """ * 5


def test_bilan_synthetic_experience_not_block() -> None:
    text = _bilan_like_text()
    out = build_structured_dataset(
        anonymized_text=text,
        original_filename="synthetic.txt",
        requested_doc_type="bilan",
        extraction_text=text,
    )
    exp = out.get("experience") or {}
    assert exp.get("level") in ("ok", "warning")
    q = out.get("quality") or {}
    assert q.get("critical_missing_fields") in ([],)


def test_compte_resultat_synthetic_has_traceability() -> None:
    t = """
    Compte de résultat
    Chiffre d'affaires 500 000
    Charges externes 80 000
    Résultat d'exploitation 40 000
    Résultat courant 38 000
    Résultat net 30 000
    """ * 4
    out = build_structured_dataset(
        anonymized_text=t,
        original_filename="cr.txt",
        requested_doc_type="compte_resultat",
        extraction_text=t,
    )
    assert out.get("doc_type") == "compte_resultat"
    exp = out.get("experience") or {}
    assert "traceability" in exp
