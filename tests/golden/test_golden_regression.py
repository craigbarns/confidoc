"""Non-régression : valeurs extraites vs golden/regression_fixtures.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.golden.compare import compare_expected_values_to_fields
from app.services.structured_dataset_service import build_structured_dataset

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "golden" / "regression_fixtures.json"


def _load_cases() -> list[dict]:
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return list(data.get("cases") or [])


_CASES = _load_cases()
_CASE_IDS = [c.get("id", f"case_{i}") for i, c in enumerate(_CASES)]


@pytest.fixture(scope="module")
def regression_cases() -> list[dict]:
    return _CASES


@pytest.mark.parametrize("case_idx", range(len(_CASES)), ids=_CASE_IDS)
def test_regression_fixture_matches_extraction(case_idx: int, regression_cases: list[dict]) -> None:
    case = regression_cases[case_idx]
    text = case["text"]
    doc_type = case["doc_type"]
    expected = case["expected_field_values"]
    # Support optional requested_doc_type override (e.g. "auto" to test routing).
    requested_doc_type = case.get("requested_doc_type") or doc_type
    out = build_structured_dataset(
        anonymized_text=text,
        original_filename=case.get("source_filename") or "fixture.txt",
        requested_doc_type=requested_doc_type,
        extraction_text=text,
    )
    assert out.get("doc_type") == doc_type, (
        f"case {case.get('id')}: routing → {out.get('doc_type')!r}, attendu {doc_type!r}"
    )
    fields = out.get("fields") or {}
    errs = compare_expected_values_to_fields(expected, fields)
    assert not errs, f"case {case.get('id')}: " + "; ".join(errs)
