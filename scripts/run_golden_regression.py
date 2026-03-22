#!/usr/bin/env python3
"""Exécute les cas golden/regression_fixtures.json (hors pytest). Code retour 0 si OK."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    from app.golden.compare import compare_expected_values_to_fields
    from app.services.structured_dataset_service import build_structured_dataset

    path = ROOT / "golden" / "regression_fixtures.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    failed = 0
    for case in cases:
        cid = case.get("id", "?")
        text = case["text"]
        doc_type = case["doc_type"]
        expected = case["expected_field_values"]
        out = build_structured_dataset(
            anonymized_text=text,
            original_filename=case.get("source_filename") or "fixture.txt",
            requested_doc_type=doc_type,
            extraction_text=text,
        )
        errs = compare_expected_values_to_fields(expected, out.get("fields") or {})
        if errs:
            failed += 1
            print(f"FAIL {cid} ({doc_type}):", "; ".join(errs), file=sys.stderr)
        else:
            print(f"OK   {cid} ({doc_type})")
    if failed:
        print(f"\n{failed}/{len(cases)} cas en échec.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
