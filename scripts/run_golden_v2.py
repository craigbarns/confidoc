#!/usr/bin/env python3
"""Runner Golden V2: cas dossier par dossier avec expected minimal et diff lisible."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_case_dirs(cases_root: Path) -> list[Path]:
    out: list[Path] = []
    for family in sorted([p for p in cases_root.iterdir() if p.is_dir()]):
        for case_dir in sorted([p for p in family.iterdir() if p.is_dir()]):
            out.append(case_dir)
    return out


def _run_case(case_dir: Path) -> tuple[str, bool, list[str]]:
    from app.golden.compare_v2 import compare_minimal_expected
    from app.services.structured_dataset_service import build_structured_dataset

    input_path = case_dir / "input.txt"
    expected_path = case_dir / "expected.min.json"
    meta_path = case_dir / "meta.json"

    if not input_path.exists() or not expected_path.exists() or not meta_path.exists():
        return case_dir.name, False, ["fichiers requis manquants (input/expected/meta)"]

    text = input_path.read_text(encoding="utf-8")
    expected = _load_json(expected_path)
    meta = _load_json(meta_path)

    requested_doc_type = str(meta.get("requested_doc_type") or expected.get("doc_type") or "auto")
    source_filename = str(meta.get("source_filename") or f"{case_dir.name}.txt")

    actual = build_structured_dataset(
        anonymized_text=text,
        original_filename=source_filename,
        requested_doc_type=requested_doc_type,
        extraction_text=text,
    )
    diffs = compare_minimal_expected(expected, actual)
    return case_dir.name, len(diffs) == 0, diffs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run golden v2 minimal checks")
    parser.add_argument(
        "--cases-root",
        default=str(ROOT / "golden" / "cases"),
        help="Root directory containing golden case folders",
    )
    parser.add_argument(
        "--case-id",
        default="",
        help="Run a single case by directory name (e.g. 2072_clean_01)",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Run cases where meta.json has active=false (templates/drafts)",
    )
    args = parser.parse_args()

    cases_root = Path(args.cases_root)
    if not cases_root.exists():
        print(f"Cases root not found: {cases_root}", file=sys.stderr)
        return 2

    case_dirs = _discover_case_dirs(cases_root)
    if args.case_id:
        case_dirs = [p for p in case_dirs if p.name == args.case_id]
        if not case_dirs:
            print(f"Case not found: {args.case_id}", file=sys.stderr)
            return 2

    # Skip draft/template cases unless explicitly requested.
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
    for case_dir in case_dirs:
        cid, ok, diffs = _run_case(case_dir)
        if ok:
            print(f"PASS {cid}")
        else:
            failed += 1
            print(f"FAIL {cid}")
            for d in diffs:
                print(f"  - {d}")

    print(f"\nSummary: {total - failed}/{total} pass, {failed} fail, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

