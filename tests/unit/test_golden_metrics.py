"""Tests for Golden V2 structured quality metrics."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.golden.compare_v2 import score_minimal_expected


def _load_run_golden_v2_module():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "run_golden_v2.py"
    spec = importlib.util.spec_from_file_location("run_golden_v2_for_tests", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_score_minimal_expected_counts_field_exact_matches() -> None:
    expected = {
        "doc_type": "liasse_fiscale",
        "extractor_name": "llm:mistral-large",
        "critical_fields": {
            "total_actif": 1000,
            "resultat_exercice": -50,
            "societe": "WEMADE",
        },
        "quality": {"needs_review": False, "ready_for_ai": True},
    }
    actual = {
        "doc_type": "liasse_fiscale",
        "provenance": {"extractor_name": "llm:mistral-large"},
        "fields": {
            "total_actif": {"value": 1000.2},
            "resultat_exercice": {"value": -51},
            "societe": {"value": "WEMADE"},
        },
        "quality": {"needs_review": False, "ready_for_ai": True},
    }

    score = score_minimal_expected(expected, actual)

    assert score["pass"] is False
    assert score["total_checks"] == 7
    assert score["passed_checks"] == 6
    assert score["failed_checks"] == 1
    assert score["check_pass_rate"] == 6 / 7 * 100
    assert score["diffs"] == ["critical_fields.resultat_exercice: attendu=-50 obtenu=-51"]


def test_aggregate_metrics_exposes_field_and_document_rates() -> None:
    run_golden_v2 = _load_run_golden_v2_module()
    results = [
        {
            "case_id": "case_ok",
            "pass": True,
            "doc_type": "liasse_fiscale",
            "checks": [
                {"category": "critical_field", "name": "total_actif", "passed": True},
                {"category": "critical_field", "name": "resultat_exercice", "passed": True},
                {"category": "quality", "name": "ready_for_ai", "passed": True},
            ],
        },
        {
            "case_id": "case_ko",
            "pass": False,
            "doc_type": "liasse_fiscale",
            "checks": [
                {"category": "critical_field", "name": "total_actif", "passed": False},
                {"category": "critical_field", "name": "resultat_exercice", "passed": True},
                {"category": "quality", "name": "ready_for_ai", "passed": False},
            ],
        },
    ]

    metrics = run_golden_v2._aggregate_metrics(results)

    assert metrics["case_pass_rate"] == 50.0
    assert metrics["critical_field_exact_match_rate"] == 75.0
    assert metrics["quality_check_pass_rate"] == 50.0
    assert metrics["by_critical_field"]["total_actif"]["pass_rate"] == 50.0
    assert metrics["by_critical_field"]["resultat_exercice"]["pass_rate"] == 100.0
    assert metrics["by_doc_type"]["liasse_fiscale"]["pass_rate"] == 50.0
