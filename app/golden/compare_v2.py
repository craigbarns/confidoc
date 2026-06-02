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


def compare_minimal_expected(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Return list of diffs; empty list means PASS."""
    diffs: list[str] = []

    exp_doc_type = expected.get("doc_type")
    if exp_doc_type is not None and actual.get("doc_type") != exp_doc_type:
        diffs.append(f"doc_type: attendu={exp_doc_type!r} obtenu={actual.get('doc_type')!r}")

    exp_extractor = expected.get("extractor_name")
    act_extractor = (actual.get("provenance") or {}).get("extractor_name")
    if exp_extractor is not None and act_extractor != exp_extractor:
        diffs.append(f"extractor_name: attendu={exp_extractor!r} obtenu={act_extractor!r}")

    # Critical fields
    exp_fields = expected.get("critical_fields") or {}
    act_fields = actual.get("fields") or {}
    for key, exp_val in exp_fields.items():
        got = (act_fields.get(key) or {}).get("value")
        if exp_val is None:
            if got not in (None, "", []):
                diffs.append(f"critical_fields.{key}: attendu=null obtenu={got!r}")
            continue
        if isinstance(exp_val, (int, float)):
            if not _num_close(exp_val, got):
                diffs.append(f"critical_fields.{key}: attendu={exp_val!r} obtenu={got!r}")
            continue
        if _norm(exp_val) != _norm(got):
            diffs.append(f"critical_fields.{key}: attendu={exp_val!r} obtenu={got!r}")

    # Quality block
    exp_q = expected.get("quality") or {}
    act_q = actual.get("quality") or {}

    if "critical_missing_fields" in exp_q:
        exp_missing = set(exp_q.get("critical_missing_fields") or [])
        got_missing = set(act_q.get("critical_missing_fields") or [])
        if exp_missing != got_missing:
            diffs.append(
                "quality.critical_missing_fields: "
                f"attendu={sorted(exp_missing)!r} obtenu={sorted(got_missing)!r}"
            )

    if "quality_flags_must_include" in exp_q:
        must = set(exp_q.get("quality_flags_must_include") or [])
        got = set(act_q.get("quality_flags") or [])
        missing = sorted(must - got)
        if missing:
            diffs.append(f"quality_flags_must_include manquants={missing!r}")

    if "quality_flags_must_exclude" in exp_q:
        must_not = set(exp_q.get("quality_flags_must_exclude") or [])
        got = set(act_q.get("quality_flags") or [])
        present = sorted(must_not & got)
        if present:
            diffs.append(f"quality_flags_must_exclude présents={present!r}")

    for flag in ("needs_review", "ready_for_ai", "ready_for_ai_core"):
        if flag in exp_q:
            exp_v = bool(exp_q.get(flag))
            got_v = bool(act_q.get(flag))
            if exp_v != got_v:
                diffs.append(f"quality.{flag}: attendu={exp_v} obtenu={got_v}")

    return diffs
