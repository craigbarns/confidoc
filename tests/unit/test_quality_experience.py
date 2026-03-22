"""Couche experience (résumé qualité FR)."""

from __future__ import annotations

from app.services.quality_experience import build_quality_experience


def test_experience_ok_when_ready() -> None:
    exp = build_quality_experience(
        doc_type="compte_resultat",
        quality={
            "needs_review": False,
            "ready_for_ai": True,
            "quality_flags": [],
            "critical_missing_fields": [],
            "coverage_ratio": 0.9,
        },
        provenance={"extractor_name": "x"},
    )
    assert exp["level"] == "ok"
    assert "prête" in exp["headline_fr"].lower() or "alignée" in exp["headline_fr"].lower()


def test_experience_block_when_critical() -> None:
    exp = build_quality_experience(
        doc_type="bilan",
        quality={
            "needs_review": True,
            "ready_for_ai": False,
            "quality_flags": ["critical_fields_missing"],
            "critical_missing_fields": ["total_actif"],
            "coverage_ratio": 0.3,
        },
        provenance={},
    )
    assert exp["level"] == "block"
    assert "champ" in exp["headline_fr"].lower()


def test_segmentation_note_fallback() -> None:
    exp = build_quality_experience(
        doc_type="bilan",
        quality={"needs_review": True, "ready_for_ai": False, "quality_flags": [], "critical_missing_fields": []},
        provenance={
            "text_segmentation": {
                "strategy": "semantic_window",
                "fallback_to_full_text": True,
                "full_chars": 20000,
                "segment_chars": 5000,
            }
        },
    )
    assert exp["segmentation_note_fr"] is not None
    assert "intégral" in (exp["segmentation_note_fr"] or "").lower()
