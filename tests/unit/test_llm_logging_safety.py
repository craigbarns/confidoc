"""Regression tests for LLM log minimization."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.services import llm_anonymization_service, llm_extraction_service


def test_llm_response_fingerprint_does_not_include_raw_content() -> None:
    raw = "Jean Dupont claire.moreau@example.fr"

    extraction = llm_extraction_service._response_fingerprint(raw)
    anonymization = llm_anonymization_service._response_fingerprint(raw)

    expected_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert extraction == {"response_sha256": expected_hash, "response_chars": len(raw)}
    assert anonymization == {"response_sha256": expected_hash, "response_chars": len(raw)}
    assert "Jean" not in str(extraction)
    assert "claire.moreau" not in str(anonymization)


def test_llm_services_do_not_log_raw_parse_failures() -> None:
    root = Path(__file__).resolve().parents[2]
    extraction_source = (root / "app/services/llm_extraction_service.py").read_text()
    anonymization_source = (root / "app/services/llm_anonymization_service.py").read_text()

    assert "raw_response[:200]" not in extraction_source
    assert "raw_response[:200]" not in anonymization_source
    assert "raw=raw_response" not in extraction_source
    assert "raw=raw_response" not in anonymization_source
