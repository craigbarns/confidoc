#!/usr/bin/env python3
"""Score and promote OCR stress Golden drafts.

This script evaluates `golden/cases/ocr_stress/*` drafts and can promote a
selected subset to active golden cases with minimal expectations.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASES_ROOT = ROOT / "golden" / "cases"
REPORT_PATH = ROOT / "golden" / "OCR_STRESS_CURATION_REPORT.md"


@dataclass
class Candidate:
    case_dir: Path
    case_id: str
    source: str
    score: float
    output: dict[str, Any]
    notes: list[str]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _discover_cases(family_dir: Path) -> list[Path]:
    if not family_dir.exists():
        return []
    return sorted([p for p in family_dir.iterdir() if p.is_dir()])


def _extract_source(meta: dict[str, Any]) -> str:
    tags = meta.get("tags") or []
    if isinstance(tags, list):
        for t in tags:
            s = str(t).strip().lower()
            if s in {"funsd", "sroie", "docvqa"}:
                return s
    imp = meta.get("import")
    if isinstance(imp, dict):
        ds = str(imp.get("dataset") or "").lower()
        for s in ("funsd", "sroie", "docvqa"):
            if s in ds:
                return s
    return "unknown"


def _build_expected_min(output: dict[str, Any]) -> dict[str, Any]:
    fields = output.get("fields") or {}
    quality = output.get("quality") or {}
    prov = output.get("provenance") or {}

    critical_fields: dict[str, Any] = {}
    for k, meta in fields.items():
        if not isinstance(meta, dict):
            continue
        v = meta.get("value")
        if v in (None, "", []):
            continue
        if isinstance(v, (int, float, str, bool)):
            critical_fields[str(k)] = v
        if len(critical_fields) >= 4:
            break

    return {
        "doc_type": output.get("doc_type"),
        "extractor_name": prov.get("extractor_name"),
        "critical_fields": critical_fields,
        "quality": {
            "critical_missing_fields": quality.get("critical_missing_fields", []),
            "needs_review": bool(quality.get("needs_review", True)),
            "ready_for_ai": bool(quality.get("ready_for_ai", False)),
            "ready_for_ai_core": bool(quality.get("ready_for_ai_core", False)),
        },
    }


def _score_output(output: dict[str, Any], text_len: int) -> tuple[float, list[str]]:
    q = output.get("quality") or {}
    doc_type = str(output.get("doc_type") or "unknown")
    fields = output.get("fields") or {}
    filled = 0
    for meta in fields.values():
        if isinstance(meta, dict) and meta.get("value") not in (None, "", []):
            filled += 1

    score = 0.0
    notes: list[str] = []
    cov = float(q.get("coverage_ratio") or 0.0)
    score += cov * 100.0
    notes.append(f"coverage={cov:.3f}")

    if bool(q.get("ready_for_ai_core", False)):
        score += 80.0
        notes.append("core_ready")
    if bool(q.get("ready_for_ai", False)):
        score += 60.0
        notes.append("full_ready")
    if not bool(q.get("needs_review", True)):
        score += 20.0
        notes.append("no_review")

    score += min(filled, 8) * 4.0
    notes.append(f"filled={filled}")

    if doc_type.startswith("unknown"):
        score -= 35.0
        notes.append("unknown_doc_type_penalty")
    else:
        score += 20.0
        notes.append(f"doc_type={doc_type}")

    if text_len < 180:
        score -= 25.0
        notes.append("short_text_penalty")
    return score, notes


def _curate(
    *,
    family_dir: Path,
    max_total: int,
    max_per_source: int,
    promote: bool,
) -> tuple[list[Candidate], list[str]]:
    from app.services.structured_dataset_service import build_structured_dataset

    candidates: list[Candidate] = []
    errors: list[str] = []
    for case_dir in _discover_cases(family_dir):
        meta_path = case_dir / "meta.json"
        input_path = case_dir / "input.txt"
        expected_path = case_dir / "expected.min.json"
        if not (meta_path.exists() and input_path.exists() and expected_path.exists()):
            continue

        try:
            meta = _load_json(meta_path)
            if bool(meta.get("active", True)):
                continue
            text = input_path.read_text(encoding="utf-8")
            source_filename = str(meta.get("source_filename") or f"{case_dir.name}.txt")
            out = build_structured_dataset(
                anonymized_text=text,
                original_filename=source_filename,
                requested_doc_type="auto",
                extraction_text=text,
            )
            score, notes = _score_output(out, len(text))
            candidates.append(
                Candidate(
                    case_dir=case_dir,
                    case_id=str(meta.get("id") or case_dir.name),
                    source=_extract_source(meta),
                    score=score,
                    output=out,
                    notes=notes,
                )
            )
        except Exception as exc:
            errors.append(f"{case_dir.name}: {exc}")

    per_source: dict[str, list[Candidate]] = defaultdict(list)
    for c in sorted(candidates, key=lambda x: x.score, reverse=True):
        per_source[c.source].append(c)

    selected: list[Candidate] = []
    for src, items in sorted(per_source.items()):
        selected.extend(items[:max_per_source])

    selected = sorted(selected, key=lambda x: x.score, reverse=True)[:max_total]

    if promote:
        now = datetime.now(UTC).isoformat()
        for c in selected:
            meta_path = c.case_dir / "meta.json"
            expected_path = c.case_dir / "expected.min.json"
            meta = _load_json(meta_path)
            meta["active"] = True
            meta["notes"] = str(meta.get("notes") or "") + f" [promoted:{now}]"
            _write_json(meta_path, meta)
            _write_json(expected_path, _build_expected_min(c.output))

    return selected, errors


def _build_report(
    *,
    selected: list[Candidate],
    errors: list[str],
    max_total: int,
    max_per_source: int,
    promote: bool,
) -> str:
    lines = [
        "# OCR Stress Curation Report",
        "",
        f"- Generated at: {datetime.now(UTC).isoformat()}",
        f"- Mode: {'PROMOTE' if promote else 'ANALYZE'}",
        f"- Selection target: max_total={max_total}, max_per_source={max_per_source}",
        f"- Selected cases: {len(selected)}",
        "",
        "## Selected cases",
        "",
    ]
    if not selected:
        lines.append("- None")
    else:
        for c in selected:
            rel = c.case_dir.relative_to(ROOT)
            lines.append(
                f"- `{rel}` | source={c.source} | score={c.score:.1f} | "
                f"doc_type={c.output.get('doc_type')} | "
                f"ready_core={bool((c.output.get('quality') or {}).get('ready_for_ai_core', False))}"
            )
            lines.append(f"  - notes: {', '.join(c.notes)}")
    lines.append("")

    if errors:
        lines.extend(["## Errors", ""])
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")

    lines.extend(
        [
            "## Next steps",
            "",
            "- Review promoted expected files if running in PROMOTE mode.",
            "- Run: `python scripts/run_golden_v2.py --include-inactive` to inspect full OCR stress behavior.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate OCR stress golden drafts.")
    parser.add_argument("--family", default="ocr_stress", help="Golden family folder name.")
    parser.add_argument("--max-total", type=int, default=12, help="Max selected cases.")
    parser.add_argument(
        "--max-per-source",
        type=int,
        default=4,
        help="Max selected per source key.",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Apply promotion: write expected.min.json and set active=true.",
    )
    parser.add_argument(
        "--report-path",
        default=str(REPORT_PATH),
        help="Markdown report output path.",
    )
    args = parser.parse_args()

    family_dir = CASES_ROOT / args.family
    selected, errors = _curate(
        family_dir=family_dir,
        max_total=max(1, int(args.max_total)),
        max_per_source=max(1, int(args.max_per_source)),
        promote=bool(args.promote),
    )
    report_text = _build_report(
        selected=selected,
        errors=errors,
        max_total=max(1, int(args.max_total)),
        max_per_source=max(1, int(args.max_per_source)),
        promote=bool(args.promote),
    )
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text + "\n", encoding="utf-8")

    print(f"Selected: {len(selected)}")
    if errors:
        print(f"Errors: {len(errors)}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
