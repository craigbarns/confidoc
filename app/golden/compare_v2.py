"""Comparaison ciblée golden v2 (doc_type, champs critiques, qualité, extracteur)."""

from __future__ import annotations

import math
from typing import Any


def _norm(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit() and len(s) == 4:
            try:
                return int(s)
            except ValueError:
                return s
        return s
    return v


def _num_close(a: Any, b: Any, *, rel_tol: float = 1e-5, abs_tol: float = 0.51) -> bool:
    try:
        fa = float(_norm(a))  # type: ignore[arg-type]
        fb = float(_norm(b))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if math.isnan(fa) or math.isnan(fb):
        return False
    return math.isclose(fa, fb, rel_tol=rel_tol, abs_tol=abs_tol)


def _critical_field_matches(expected_value: Any, actual_value: Any) -> bool:
    if expected_value is None:
        return actual_value in (None, "", [])
    if isinstance(expected_value, (int, float)):
        return _num_close(expected_value, actual_value)
    return _norm(expected_value) == _norm(actual_value)


def _check(
    checks: list[dict[str, Any]],
    diffs: list[str],
    *,
    category: str,
    name: str,
    passed: bool,
    diff: str | None = None,
) -> None:
    checks.append({"category": category, "name": name, "passed": passed})
    if not passed and diff:
        diffs.append(diff)


def score_minimal_expected(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """Return structured exact-match scores plus the historical diff list."""
    diffs: list[str] = []
    checks: list[dict[str, Any]] = []

    exp_doc_type = expected.get("doc_type")
    if exp_doc_type is not None:
        got_doc_type = actual.get("doc_type")
        _check(
            checks,
            diffs,
            category="doc_type",
            name="doc_type",
            passed=got_doc_type == exp_doc_type,
            diff=f"doc_type: attendu={exp_doc_type!r} obtenu={got_doc_type!r}",
        )

    exp_extractor = expected.get("extractor_name")
    act_extractor = (actual.get("provenance") or {}).get("extractor_name")
    if exp_extractor is not None:
        _check(
            checks,
            diffs,
            category="extractor_name",
            name="extractor_name",
            passed=act_extractor == exp_extractor,
            diff=f"extractor_name: attendu={exp_extractor!r} obtenu={act_extractor!r}",
        )

    # Critical fields
    exp_fields = expected.get("critical_fields") or {}
    act_fields = actual.get("fields") or {}
    for key, exp_val in exp_fields.items():
        got = (act_fields.get(key) or {}).get("value")
        passed = _critical_field_matches(exp_val, got)
        expected_label = "null" if exp_val is None else repr(exp_val)
        _check(
            checks,
            diffs,
            category="critical_field",
            name=str(key),
            passed=passed,
            diff=f"critical_fields.{key}: attendu={expected_label} obtenu={got!r}",
        )

    # Quality block
    exp_q = expected.get("quality") or {}
    act_q = actual.get("quality") or {}

    if "critical_missing_fields" in exp_q:
        exp_missing = set(exp_q.get("critical_missing_fields") or [])
        got_missing = set(act_q.get("critical_missing_fields") or [])
        _check(
            checks,
            diffs,
            category="quality",
            name="critical_missing_fields",
            passed=exp_missing == got_missing,
            diff=(
                "quality.critical_missing_fields: "
                f"attendu={sorted(exp_missing)!r} obtenu={sorted(got_missing)!r}"
            ),
        )

    if "quality_flags_must_include" in exp_q:
        must = set(exp_q.get("quality_flags_must_include") or [])
        got = set(act_q.get("quality_flags") or [])
        missing = sorted(must - got)
        _check(
            checks,
            diffs,
            category="quality",
            name="quality_flags_must_include",
            passed=not missing,
            diff=f"quality_flags_must_include manquants={missing!r}",
        )

    if "quality_flags_must_exclude" in exp_q:
        must_not = set(exp_q.get("quality_flags_must_exclude") or [])
        got = set(act_q.get("quality_flags") or [])
        present = sorted(must_not & got)
        _check(
            checks,
            diffs,
            category="quality",
            name="quality_flags_must_exclude",
            passed=not present,
            diff=f"quality_flags_must_exclude présents={present!r}",
        )

    for flag in ("needs_review", "ready_for_ai", "ready_for_ai_core"):
        if flag in exp_q:
            exp_v = bool(exp_q.get(flag))
            got_v = bool(act_q.get(flag))
            _check(
                checks,
                diffs,
                category="quality",
                name=flag,
                passed=exp_v == got_v,
                diff=f"quality.{flag}: attendu={exp_v} obtenu={got_v}",
            )

    total_checks = len(checks)
    passed_checks = sum(1 for item in checks if item["passed"])
    failed_checks = total_checks - passed_checks

    return {
        "pass": failed_checks == 0,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "check_pass_rate": (passed_checks / total_checks * 100) if total_checks else 100.0,
        "checks": checks,
        "diffs": diffs,
    }


def compare_minimal_expected(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Return list of diffs; empty list means PASS."""
    score = score_minimal_expected(expected, actual)
    return list(score["diffs"])
