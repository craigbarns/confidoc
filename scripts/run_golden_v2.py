#!/usr/bin/env python3
"""Runner Golden V2/V3: cas dossier par dossier avec extraction LLM et diff lisible."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
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
            "ready_for_ai_core": ready or (confiance == "medium"), # Plus permissif pour 'core'
        }
    }


async def _run_case(case_dir: Path) -> tuple[str, bool, list[str]]:
    from app.golden.compare_v2 import compare_minimal_expected
    from app.services.llm_extraction_service import extract_with_llm

    input_path = case_dir / "input.txt"
    expected_path = case_dir / "expected.min.json"
    meta_path = case_dir / "meta.json"

    if not input_path.exists() or not expected_path.exists() or not meta_path.exists():
        return case_dir.name, False, ["fichiers requis manquants (input/expected/meta)"]

    text = input_path.read_text(encoding="utf-8")
    expected = _load_json(expected_path)
    meta = _load_json(meta_path)

    source_filename = str(meta.get("source_filename") or f"{case_dir.name}.txt")

    try:
        # On utilise l'extracteur LLM actuel
        llm_out = await extract_with_llm(text)
        actual = _map_llm_to_golden(llm_out, source_filename)
        
        diffs = compare_minimal_expected(expected, actual)
        return case_dir.name, len(diffs) == 0, diffs
    except Exception as exc:
        return case_dir.name, False, [f"Erreur d'exécution: {str(exc)}"]


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
        cid, ok, diffs = await _run_case(case_dir)
        results.append({
            "case_id": cid,
            "pass": ok,
            "diffs": diffs
        })
        
        if ok:
            print(f"PASS {cid}")
        else:
            failed += 1
            print(f"FAIL {cid}")
            for d in diffs:
                print(f"  - {d}")

    pass_rate = ((total - failed) / total * 100) if total > 0 else 0
    print(f"\nSummary: {total - failed}/{total} pass ({pass_rate:.1f}%), {failed} fail, {skipped} skipped")

    if args.json_report:
        report_path = ROOT / "golden" / "latest_quality_report.json"
        report = {
            "timestamp": Path(ROOT).stat().st_mtime, # Simplifié
            "total": total,
            "passed": total - failed,
            "failed": failed,
            "pass_rate": pass_rate,
            "results": results
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report saved to {report_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(async_main()))
