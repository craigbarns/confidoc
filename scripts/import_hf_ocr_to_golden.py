#!/usr/bin/env python3
"""Import OCR stress samples from Hugging Face into Golden V2 drafts.

Generated cases are intentionally created with `active=false` so they do not
affect CI until manually reviewed and promoted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_ROOT = ROOT / "golden" / "cases"
DEFAULT_REPORT_PATH = ROOT / "golden" / "OCR_HF_IMPORT_REPORT.md"
DATASETS_SERVER = "https://datasets-server.huggingface.co"


@dataclass(frozen=True)
class SourceSpec:
    key: str
    dataset: str
    preferred_configs: tuple[str, ...]
    preferred_splits: tuple[str, ...]


SOURCES: dict[str, SourceSpec] = {
    "funsd": SourceSpec(
        key="funsd",
        dataset="nielsr/funsd",
        preferred_configs=("default",),
        preferred_splits=("train", "validation", "test"),
    ),
    "sroie": SourceSpec(
        key="sroie",
        dataset="jsdnrs/ICDAR2019-SROIE",
        preferred_configs=("default",),
        preferred_splits=("train", "validation", "test"),
    ),
    "docvqa": SourceSpec(
        key="docvqa",
        dataset="lmms-lab/DocVQA",
        preferred_configs=("default",),
        preferred_splits=("validation", "test", "train"),
    ),
}


def _http_get_json(url: str, timeout_s: float = 30.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ConfiDoc-HF-GoldenImporter/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _safe_slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "sample"


def _pick_config_and_split(spec: SourceSpec) -> tuple[str, str]:
    q = urllib.parse.urlencode({"dataset": spec.dataset})
    payload = _http_get_json(f"{DATASETS_SERVER}/splits?{q}")
    splits = payload.get("splits") or []
    if not splits:
        raise RuntimeError(f"No splits returned for {spec.dataset}")

    available: set[tuple[str, str]] = set()
    for item in splits:
        cfg = str(item.get("config") or "")
        sp = str(item.get("split") or "")
        if cfg and sp:
            available.add((cfg, sp))

    for cfg in spec.preferred_configs:
        for sp in spec.preferred_splits:
            if (cfg, sp) in available:
                return cfg, sp

    # Fallback: first discovered pair
    cfg, sp = sorted(available)[0]
    return cfg, sp


def _fetch_rows(dataset: str, config: str, split: str, n_rows: int) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode(
        {
            "dataset": dataset,
            "config": config,
            "split": split,
            "offset": "0",
            "length": str(max(1, n_rows)),
        }
    )
    payload = _http_get_json(f"{DATASETS_SERVER}/first-rows?{q}")
    rows = payload.get("rows") or []
    out: list[dict[str, Any]] = []
    for item in rows:
        row = item.get("row")
        if isinstance(row, dict):
            out.append(row)
    return out


def _extract_text_and_hints(source_key: str, row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    words = row.get("words")
    text = ""
    hints: dict[str, Any] = {}

    if isinstance(words, list):
        safe_words = [str(w).strip() for w in words if str(w).strip()]
        text = " ".join(safe_words)
        hints["words_count"] = len(safe_words)

    if source_key == "sroie":
        entities = row.get("entities")
        if isinstance(entities, dict):
            hints["entities"] = {
                k: str(v).strip() for k, v in entities.items() if str(v).strip()
            }
    elif source_key == "docvqa":
        question = row.get("question") or row.get("query")
        if isinstance(question, str) and question.strip():
            hints["question"] = question.strip()
        answers = row.get("answers")
        if isinstance(answers, list):
            cleaned = [str(a).strip() for a in answers if str(a).strip()]
            if cleaned:
                hints["answers"] = cleaned[:3]
    elif source_key == "funsd":
        ner_tags = row.get("ner_tags")
        if isinstance(ner_tags, list):
            hints["ner_tags_count"] = len(ner_tags)

    if not text:
        serialized = json.dumps(row, ensure_ascii=False)
        text = serialized[:12000]
        hints["fallback_serialized"] = True

    return text[:16000], hints


def _write_case(
    *,
    cases_root: Path,
    source: SourceSpec,
    split: str,
    idx: int,
    text: str,
    hints: dict[str, Any],
) -> Path:
    family_dir = cases_root / "ocr_stress"
    family_dir.mkdir(parents=True, exist_ok=True)

    case_id = f"ocr_{source.key}_{_safe_slug(split)}_{idx:03d}"
    case_dir = family_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "id": case_id,
        "requested_doc_type": "auto",
        "source_filename": f"{source.dataset}:{split}:{idx}",
        "tags": ["ocr_stress", "huggingface", source.key],
        "notes": f"OCR stress draft imported from {source.dataset} ({split}).",
        "active": False,
        "import": {
            "dataset": source.dataset,
            "split": split,
            "row_index": idx,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "hints": hints,
        },
    }
    expected_min = {}

    (case_dir / "input.txt").write_text(text.strip() + "\n", encoding="utf-8")
    (case_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (case_dir / "expected.min.json").write_text(
        json.dumps(expected_min, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return case_dir


def _build_report(
    *,
    created: list[Path],
    failed: list[str],
    spec_summaries: list[str],
) -> str:
    lines = [
        "# OCR Stress Import Report (Hugging Face)",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Cases created: {len(created)}",
        f"- Sources requested: {', '.join(spec_summaries) if spec_summaries else '-'}",
        "",
    ]
    if created:
        lines.extend(["## Created cases", ""])
        for p in created:
            lines.append(f"- `{p.relative_to(ROOT)}`")
        lines.append("")
    if failed:
        lines.extend(["## Source errors", ""])
        for err in failed:
            lines.append(f"- {err}")
        lines.append("")
    lines.extend(
        [
            "## Notes",
            "",
            "- All imported cases are drafts (`active=false`).",
            "- `expected.min.json` is intentionally empty for manual promotion.",
            "- To inspect drafts: `python scripts/run_golden_v2.py --include-inactive`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Hugging Face OCR samples as Golden draft cases."
    )
    parser.add_argument(
        "--sources",
        default="funsd,sroie,docvqa",
        help="Comma-separated source keys (available: funsd,sroie,docvqa).",
    )
    parser.add_argument(
        "--rows-per-source",
        type=int,
        default=5,
        help="How many rows to import per source.",
    )
    parser.add_argument(
        "--cases-root",
        default=str(DEFAULT_CASES_ROOT),
        help="Golden cases root directory.",
    )
    parser.add_argument(
        "--report-path",
        default=str(DEFAULT_REPORT_PATH),
        help="Markdown report output path.",
    )
    args = parser.parse_args()

    requested = [_safe_slug(x) for x in str(args.sources).split(",") if x.strip()]
    rows_per_source = max(1, int(args.rows_per_source))
    cases_root = Path(args.cases_root)
    report_path = Path(args.report_path)

    selected: list[SourceSpec] = []
    for key in requested:
        if key in SOURCES:
            selected.append(SOURCES[key])
        else:
            print(f"[WARN] Unknown source '{key}' ignored.", file=sys.stderr)

    if not selected:
        print("No valid sources selected.", file=sys.stderr)
        return 2

    created: list[Path] = []
    failed: list[str] = []
    for spec in selected:
        try:
            cfg, split = _pick_config_and_split(spec)
            rows = _fetch_rows(spec.dataset, cfg, split, rows_per_source)[:rows_per_source]
            if not rows:
                failed.append(f"{spec.key}: no rows returned for {cfg}/{split}")
                continue
            for idx, row in enumerate(rows):
                text, hints = _extract_text_and_hints(spec.key, row)
                case_dir = _write_case(
                    cases_root=cases_root,
                    source=spec,
                    split=split,
                    idx=idx,
                    text=text,
                    hints=hints,
                )
                created.append(case_dir)
        except Exception as exc:  # pragma: no cover - network/system dependent
            failed.append(f"{spec.key}: {exc}")

    report = _build_report(
        created=created,
        failed=failed,
        spec_summaries=[s.key for s in selected],
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report + "\n", encoding="utf-8")

    print(f"Created {len(created)} draft case(s).")
    if failed:
        print(f"Sources with errors: {len(failed)}")
        for item in failed:
            print(f"  - {item}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

