"""Repli texte entier vs fenêtre sémantique (qualité)."""

from __future__ import annotations

from app.services.structured_dataset_service import _extraction_quality_better


def test_better_fewer_critical_missing() -> None:
    a = {"critical_missing_fields": ["x", "y"], "coverage_ratio": 0.9}
    b = {"critical_missing_fields": ["x"], "coverage_ratio": 0.5}
    assert _extraction_quality_better(b, a) is True
    assert _extraction_quality_better(a, b) is False


def test_same_critical_prefers_coverage() -> None:
    a = {"critical_missing_fields": [], "coverage_ratio": 0.4}
    b = {"critical_missing_fields": [], "coverage_ratio": 0.75}
    assert _extraction_quality_better(b, a) is True
    assert _extraction_quality_better(a, b) is False


def test_equal_is_not_better() -> None:
    q = {"critical_missing_fields": [], "coverage_ratio": 0.5}
    assert _extraction_quality_better(q, q) is False
