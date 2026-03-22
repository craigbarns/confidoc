"""Schémas Ollama + extraction JSON."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.ollama_schemas import AuditResult, SummaryResult
from app.services.ollama_service import extract_json_object_from_llm


def test_summary_coerce_confidence_percent() -> None:
    m = SummaryResult.model_validate(
        {
            "resume_executif": "ok",
            "points_cles": [],
            "anomalies_ou_alertes": [],
            "questions_de_revue": [],
            "confiance_globale": 75,
        }
    )
    assert m.confiance_globale == pytest.approx(0.75)


def test_audit_requires_checks() -> None:
    with pytest.raises(ValidationError):
        AuditResult.model_validate({"global_status": "inconclusive", "checks": []})


def test_extract_json_strips_noise() -> None:
    raw = 'Here:\n{"a": 1, "b": 2}\nThanks'
    assert extract_json_object_from_llm(raw) == {"a": 1, "b": 2}
