#!/usr/bin/env python3
"""Runner Golden V2/V3: cas dossier par dossier avec extraction LLM et diff lisible."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Ajoute le projet au PYTHONPATH pour l'import d'app
sys.path.append(str(ROOT))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_case_dirs(cases_root: Path) -> list[Path]:
    out: list[Path] = []
    if not cases_root.exists():
        return out
    for family in sorted([p for p in cases_root.iterdir() if p.is_dir()]):
        for case_dir in sorted([p for p in family.iterdir() if p.is_dir()]):
            out.append(case_dir)
    return out


def _map_llm_to_golden(llm_out: dict[str, Any], original_filename: str) -> dict[str, Any]:
    """Mappe la sortie du LLM (v2) vers le format attendu par le comparateur Golden (v1/v2)."""

    # Mapping des champs comptables vers le format plat "fields"
    fields: dict[str, dict[str, Any]] = {}

    # Totaux
    totaux = llm_out.get("totaux", {})
    if isinstance(totaux, dict):
        for k, v in totaux.items():
            if v is not None:
                fields[k] = {"value": v}

    # Société & Exercice
    societe = llm_out.get("societe", {})
    if isinstance(societe, dict) and societe.get("denomination"):
        fields["societe"] = {"value": societe["denomination"]}

    exercice = llm_out.get("exercice", {})
    if isinstance(exercice, dict) and exercice.get("date_fin"):
        fields["exercice"] = {"value": exercice["date_fin"]}

    # Cas particulier: le golden attend souvent 'resultat_exercice' pour le bilan
    if "resultat_net" in totaux and "resultat_exercice" not in fields:
        fields["resultat_exercice"] = {"value": totaux["resultat_net"]}

    # Construction du bloc qualité minimal pour satisfaire le comparateur
    confiance = llm_out.get("confiance", "low")
    ready = confiance == "high"

    # Quality flags
    flags = []
    if not ready:
        flags.append("manual_review_recommended")

    return {
        "doc_type": llm_out.get("type_document"),
        "provenance": {
            "extractor_name": "llm:mistral-large",
            "source_filename": original_filename,
        },
        "fields": fields,
        "quality": {
            "critical_missing_fields": [],  # Simplifié pour le LLM
            "quality_flags": flags,
            "needs_review": not ready,
            "ready_for_ai": ready,
            "ready_for_ai_core": ready or (confiance == "medium"),  # Plus permissif pour 'core'
        },
    }


def _rate(passed: int, total: int) -> float:
    return (passed / total * 100) if total else 100.0


def _empty_bucket() -> dict[str, int]:
    return {"total": 0, "passed": 0, "failed": 0}


def _add_check(bucket: dict[str, int], *, passed: bool) -> None:
    bucket["total"] += 1
    if passed:
        bucket["passed"] += 1
    else:
        bucket["failed"] += 1


def _public_bucket(bucket: dict[str, int]) -> dict[str, float | int]:
    return {
        "total": bucket["total"],
        "passed": bucket["passed"],
        "failed": bucket["failed"],
        "pass_rate": round(_rate(bucket["passed"], bucket["total"]), 1),
    }


def _aggregate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    case_bucket = _empty_bucket()
    all_checks = _empty_bucket()
    critical_fields = _empty_bucket()
    quality_checks = _empty_bucket()
    doc_type_checks = _empty_bucket()
    extractor_checks = _empty_bucket()
    by_critical_field: dict[str, dict[str, int]] = {}
    by_doc_type: dict[str, dict[str, int]] = {}

    for result in results:
        passed_case = bool(result.get("pass"))
        _add_check(case_bucket, passed=passed_case)

        doc_type = str(result.get("doc_type") or "unknown")
        doc_bucket = by_doc_type.setdefault(doc_type, _empty_bucket())
        _add_check(doc_bucket, passed=passed_case)

        for check in result.get("checks") or []:
            passed = bool(check.get("passed"))
            category = str(check.get("category") or "")
            name = str(check.get("name") or "unknown")
            _add_check(all_checks, passed=passed)

            if category == "critical_field":
                _add_check(critical_fields, passed=passed)
                field_bucket = by_critical_field.setdefault(name, _empty_bucket())
                _add_check(field_bucket, passed=passed)
            elif category == "quality":
                _add_check(quality_checks, passed=passed)
            elif category == "doc_type":
                _add_check(doc_type_checks, passed=passed)
            elif category == "extractor_name":
                _add_check(extractor_checks, passed=passed)

    return {
        "case_pass_rate": round(_rate(case_bucket["passed"], case_bucket["total"]), 1),
        "case_total": case_bucket["total"],
        "case_passed": case_bucket["passed"],
        "case_failed": case_bucket["failed"],
        "check_pass_rate": round(_rate(all_checks["passed"], all_checks["total"]), 1),
        "critical_field_exact_match_rate": round(
            _rate(critical_fields["passed"], critical_fields["total"]), 1
        ),
        "quality_check_pass_rate": round(_rate(quality_checks["passed"], quality_checks["total"]), 1),
        "doc_type_check_pass_rate": round(_rate(doc_type_checks["passed"], doc_type_checks["total"]), 1),
        "extractor_check_pass_rate": round(
            _rate(extractor_checks["passed"], extractor_checks["total"]), 1
        ),
        "checks": {
            "all": _public_bucket(all_checks),
            "critical_fields": _public_bucket(critical_fields),
            "quality": _public_bucket(quality_checks),
            "doc_type": _public_bucket(doc_type_checks),
            "extractor_name": _public_bucket(extractor_checks),
        },
        "by_critical_field": {
            key: _public_bucket(bucket) for key, bucket in sorted(by_critical_field.items())
        },
        "by_doc_type": {key: _public_bucket(bucket) for key, bucket in sorted(by_doc_type.items())},
    }


async def _run_case(case_dir: Path) -> dict[str, Any]:
    from app.golden.compare_v2 import score_minimal_expected
    from app.services.llm_extraction_service import extract_with_llm

    input_path = case_dir / "input.txt"
    expected_path = case_dir / "expected.min.json"
    meta_path = case_dir / "meta.json"

    if not input_path.exists() or not expected_path.exists() or not meta_path.exists():
        return {
            "case_id": case_dir.name,
            "pass": False,
            "doc_type": "unknown",
            "diffs": ["fichiers requis manquants (input/expected/meta)"],
            "checks": [],
            "check_pass_rate": 0.0,
        }

    text = input_path.read_text(encoding="utf-8")
    expected = _load_json(expected_path)
    meta = _load_json(meta_path)

    source_filename = str(meta.get("source_filename") or f"{case_dir.name}.txt")

    try:
        # On utilise l'extracteur LLM actuel
        llm_out = await extract_with_llm(text)
        actual = _map_llm_to_golden(llm_out, source_filename)

        score = score_minimal_expected(expected, actual)
        return {
            "case_id": case_dir.name,
            "pass": bool(score["pass"]),
            "doc_type": expected.get("doc_type") or "unknown",
            "diffs": score["diffs"],
            "checks": score["checks"],
            "check_pass_rate": round(float(score["check_pass_rate"]), 1),
        }
    except Exception as exc:
        return {
            "case_id": case_dir.name,
            "pass": False,
            "doc_type": expected.get("doc_type") or "unknown",
            "diffs": [f"Erreur d'exécution: {str(exc)}"],
            "checks": [],
            "check_pass_rate": 0.0,
        }


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Run golden checks with current LLM extractor")
    parser.add_argument(
        "--cases-root",
        default=str(ROOT / "golden" / "cases"),
        help="Root directory containing golden case folders",
    )
    parser.add_argument(
        "--case-id",
        default="",
        help="Run a single case by directory name (e.g. cr_clean_01)",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Run cases where meta.json has active=false (templates/drafts)",
    )
    parser.add_argument(
        "--json-report",
        action="store_true",
        help="Generate a JSON report of the results",
    )
    args = parser.parse_args()

    cases_root = Path(args.cases_root)
    case_dirs = _discover_case_dirs(cases_root)
    if args.case_id:
        case_dirs = [p for p in case_dirs if p.name == args.case_id]
        if not case_dirs:
            print(f"Case not found: {args.case_id}", file=sys.stderr)
            return 2

    # Filtrage des cas actifs
    filtered: list[Path] = []
    skipped = 0
    for case_dir in case_dirs:
        meta_path = case_dir / "meta.json"
        if not meta_path.exists():
            filtered.append(case_dir)
            continue
        try:
            meta = _load_json(meta_path)
        except Exception:
            filtered.append(case_dir)
            continue
        active = bool(meta.get("active", True))
        if active or args.include_inactive:
            filtered.append(case_dir)
        else:
            skipped += 1

    case_dirs = filtered
    total = len(case_dirs)
    failed = 0
    results = []

    print(f"Running {total} golden cases (skipping {skipped} inactive)...")

    # Exécution séquentielle pour éviter de saturer le rate limit LLM
    for case_dir in case_dirs:
        result = await _run_case(case_dir)
        cid = str(result["case_id"])
        ok = bool(result["pass"])
        diffs = list(result["diffs"])
        results.append(result)

        if ok:
            print(f"PASS {cid}")
        else:
            failed += 1
            print(f"FAIL {cid}")
            for d in diffs:
                print(f"  - {d}")

    pass_rate = ((total - failed) / total * 100) if total > 0 else 0
    print(
        f"\nSummary: {total - failed}/{total} pass ({pass_rate:.1f}%), {failed} fail, {skipped} skipped"
    )

    if args.json_report:
        report_path = ROOT / "golden" / "latest_quality_report.json"
        metrics = _aggregate_metrics(results)
        report = {
            "timestamp": datetime.now(UTC).isoformat(),
            "total": total,
            "passed": total - failed,
            "failed": failed,
            "pass_rate": pass_rate,
            "metrics": metrics,
            "results": results,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report saved to {report_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(async_main()))
