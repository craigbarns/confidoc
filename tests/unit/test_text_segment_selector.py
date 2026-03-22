"""Tests sélection de segment sémantique (plaquettes / liasses longues)."""

from __future__ import annotations

from app.services.text_segment_selector import MIN_CHARS_FOR_SEMANTIC_WINDOW, select_extraction_segment
from app.services.structured_dataset_service import build_structured_dataset


def test_short_text_uses_full_document() -> None:
    text = "bilan " * 100
    assert len(text) < MIN_CHARS_FOR_SEMANTIC_WINDOW
    seg, meta = select_extraction_segment(text, "bilan")
    assert seg == text
    assert meta["strategy"] == "full_text"
    assert meta["reason"] == "below_min_chars"


def test_long_plaquette_prefers_bilan_window() -> None:
    filler = ("introduction plaquette société " * 400) + "\n"
    bilan_block = """
    BILAN — situation patrimoniale
    Total de l'actif 12 450 000
    Total du passif 12 450 000
    Capitaux propres 3 200 000
    Dettes financières 1 100 000
    """
    cr_block = """
    Compte de résultat
    Chiffre d'affaires 8 900 000
    Charges externes 1 200 000
    Résultat d'exploitation 400 000
    Résultat courant 350 000
    Résultat net 280 000
    """
    long_doc = filler + bilan_block + filler + cr_block + filler
    assert len(long_doc) >= MIN_CHARS_FOR_SEMANTIC_WINDOW

    seg, meta = select_extraction_segment(long_doc, "bilan")
    assert meta["strategy"] == "semantic_window"
    assert "total de l'actif" in seg.lower()
    assert "12 450 000" in seg or "12450000" in seg.replace(" ", "")


def test_long_plaquette_prefers_cr_window() -> None:
    filler = ("notes de bas de page " * 400) + "\n"
    bilan_block = """
    Bilan
    Total de l'actif 1 000
    Total du passif 1 000
    """
    cr_block = """
    Compte de résultat consolidé
    Chiffre d'affaires 9 000 000
    Charges externes 2 000 000
    Résultat d'exploitation 500 000
    Résultat courant 480 000
    Résultat net 400 000
    """
    long_doc = filler + bilan_block + filler + cr_block + filler
    assert len(long_doc) >= MIN_CHARS_FOR_SEMANTIC_WINDOW

    seg, meta = select_extraction_segment(long_doc, "compte_resultat")
    assert meta["strategy"] == "semantic_window"
    assert "compte de résultat" in seg.lower()
    assert "chiffre d'affaires" in seg.lower()


def test_build_structured_dataset_includes_segmentation_provenance() -> None:
    filler = ("word " * 3000) + "\n"
    bilan_block = """
    Bilan annuel
    Total de l'actif 5000
    Total du passif 5000
    Capitaux propres 1000
    """
    original = filler + bilan_block + filler
    anon = original  # pas d'anonymisation dans ce test
    out = build_structured_dataset(
        anonymized_text=anon,
        original_filename="plaquette.pdf",
        requested_doc_type="bilan",
        extraction_text=original,
    )
    prov = out.get("provenance") or {}
    seg = prov.get("text_segmentation")
    assert seg is not None
    assert seg.get("strategy") in ("semantic_window", "full_text")
    if seg.get("strategy") == "semantic_window":
        assert seg.get("segment_chars", 0) < seg.get("full_chars", 0)
