#!/usr/bin/env python3
"""Benchmark OCR engines on real accounting PDFs for ConfiDoc extraction quality."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.services.structured_dataset_service import build_structured_dataset

from app.services.anonymization_service import (
    _ocr_image,
    convert_from_bytes,
    extract_text_from_file,
)


@dataclass
class BenchCase:
    path: str
    doc_type: str


@dataclass
class BenchResult:
    case_path: str
    requested_doc_type: str
    engine: str
    ok: bool
    error: str | None
    elapsed_ms: int
    chars: int
    words: int
    coverage_ratio: float | None
    critical_missing_count: int | None
    ready_for_ai_core: bool | None
    ready_for_ai: bool | None
    detected_doc_type: str | None
    extractor_name: str | None


def _load_cases(manifest: Path) -> list[BenchCase]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Le manifest doit etre une liste JSON.")
    out: list[BenchCase] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        p = str(row.get("path") or "").strip()
        dt = str(row.get("doc_type") or "auto").strip()
        if p:
            out.append(BenchCase(path=p, doc_type=dt))
    if not out:
        raise ValueError("Aucun cas valide dans le manifest.")
    return out


def _extract_native(content: bytes, ext: str) -> str:
    return extract_text_from_file(content, ext)


def _extract_tesseract_forced(content: bytes, dpi: int, lang: str) -> str:
    images = convert_from_bytes(content, dpi=dpi)
    chunks: list[str] = []
    for i, img in enumerate(images):
        txt = _ocr_image(img, lang=lang)
        chunks.append(f"---PAGE {i + 1}---\n{txt}")
    return "\n".join(chunks).strip()


def _extract_pdfplumber(content: bytes) -> str:
    import io

    import pdfplumber

    out: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for i, page in enumerate(pdf.pages):
            txt = page.extract_text() or ""
            out.append(f"---PAGE {i + 1}---\n{txt}")
    return "\n".join(out).strip()


def _extract_doctr(content: bytes) -> str:
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor

    model = ocr_predictor(pretrained=True)
    doc = DocumentFile.from_pdf(content)
    result = model(doc)
    payload = result.export()
    lines: list[str] = []
    for pi, page in enumerate(payload.get("pages", []), start=1):
        page_lines: list[str] = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = [w.get("value", "") for w in line.get("words", []) if w.get("value")]
                if words:
                    page_lines.append(" ".join(words))
        lines.append(f"---PAGE {pi}---\n" + "\n".join(page_lines))
    return "\n".join(lines).strip()


def _extract_paddle(content: bytes, lang: str) -> str:
    import tempfile

    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_angle_cls=True, lang="fr" if "fra" in lang else "en")
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "input.pdf"
        pdf_path.write_bytes(content)
        result = ocr.ocr(str(pdf_path), cls=True)
    pages: list[str] = []
    for i, page in enumerate(result or [], start=1):
        lines: list[str] = []
        for item in page or []:
            if len(item) >= 2 and item[1] and len(item[1]) >= 1:
                lines.append(str(item[1][0]))
        pages.append(f"---PAGE {i}---\n" + "\n".join(lines))
    return "\n".join(pages).strip()


def _run_engine(
    engine: str,
    content: bytes,
    ext: str,
    case_path: str,
    doc_type: str,
    dpi: int,
    lang: str,
) -> BenchResult:
    started = time.perf_counter()
    try:
        if engine == "native":
            text = _extract_native(content, ext)
        elif engine == "tesseract":
            text = _extract_tesseract_forced(content, dpi=dpi, lang=lang)
        elif engine == "pdfplumber":
            text = _extract_pdfplumber(content)
        elif engine == "doctr":
            text = _extract_doctr(content)
        elif engine == "paddle":
            text = _extract_paddle(content, lang=lang)
        else:
            raise ValueError(f"Moteur inconnu: {engine}")
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return BenchResult(
            case_path=case_path,
            requested_doc_type=doc_type,
            engine=engine,
            ok=False,
            error=str(exc),
            elapsed_ms=elapsed,
            chars=0,
            words=0,
            coverage_ratio=None,
            critical_missing_count=None,
            ready_for_ai_core=None,
            ready_for_ai=None,
            detected_doc_type=None,
            extractor_name=None,
        )

    ds = build_structured_dataset(
        anonymized_text=text,
        original_filename=Path(case_path).name,
        requested_doc_type=doc_type,
        extraction_text=text,
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    quality = ds.get("quality", {}) if isinstance(ds, dict) else {}
    prov = ds.get("provenance", {}) if isinstance(ds, dict) else {}
    return BenchResult(
        case_path=case_path,
        requested_doc_type=doc_type,
        engine=engine,
        ok=True,
        error=None,
        elapsed_ms=elapsed,
        chars=len(text),
        words=len(text.split()),
        coverage_ratio=quality.get("coverage_ratio"),
        critical_missing_count=len(quality.get("critical_missing_fields", [])),
        ready_for_ai_core=quality.get("ready_for_ai_core"),
        ready_for_ai=quality.get("ready_for_ai"),
        detected_doc_type=ds.get("detected_doc_type"),
        extractor_name=prov.get("extractor_name"),
    )


def _write_reports(results: list[BenchResult], output_json: Path, output_md: Path) -> None:
    output_json.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines: list[str] = []
    lines.append("# OCR Benchmark Report")
    lines.append("")
    lines.append(
        "| Case | DocType | Engine | OK | ms | Words | Coverage | MissingCritical | CoreReady | ReadyAI |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        lines.append(
            f"| {Path(r.case_path).name} | {r.requested_doc_type} | {r.engine} | "
            f"{'yes' if r.ok else 'no'} | {r.elapsed_ms} | {r.words} | "
            f"{'' if r.coverage_ratio is None else round(r.coverage_ratio, 3)} | "
            f"{'' if r.critical_missing_count is None else r.critical_missing_count} | "
            f"{'' if r.ready_for_ai_core is None else ('yes' if r.ready_for_ai_core else 'no')} | "
            f"{'' if r.ready_for_ai is None else ('yes' if r.ready_for_ai else 'no')} |"
        )
        if r.error:
            lines.append(f"| ↳ error |  |  |  |  |  |  |  |  | `{r.error}` |")
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark OCR engines for ConfiDoc extraction")
    parser.add_argument(
        "--manifest",
        default="golden/ocr_benchmark_manifest.json",
        help='Manifest JSON list: [{"path": "...pdf", "doc_type": "bilan"}]',
    )
    parser.add_argument(
        "--engines",
        default="native,tesseract,pdfplumber,doctr,paddle",
        help="Comma-separated engines: native,tesseract,pdfplumber,doctr,paddle",
    )
    parser.add_argument("--ocr-dpi", type=int, default=300, help="DPI for forced tesseract OCR")
    parser.add_argument("--ocr-lang", default="fra+eng", help="OCR lang pack")
    parser.add_argument(
        "--output-json",
        default="golden/OCR_BENCHMARK_REPORT.json",
        help="JSON output report path",
    )
    parser.add_argument(
        "--output-md",
        default="golden/OCR_BENCHMARK_REPORT.md",
        help="Markdown output report path",
    )
    args = parser.parse_args()

    manifest = Path(args.manifest)
    if not manifest.exists():
        raise SystemExit(f"Manifest introuvable: {manifest}")
    cases = _load_cases(manifest)
    engines = [e.strip() for e in str(args.engines).split(",") if e.strip()]

    results: list[BenchResult] = []
    for case in cases:
        p = Path(case.path)
        if not p.exists():
            results.append(
                BenchResult(
                    case_path=case.path,
                    requested_doc_type=case.doc_type,
                    engine="all",
                    ok=False,
                    error="file_not_found",
                    elapsed_ms=0,
                    chars=0,
                    words=0,
                    coverage_ratio=None,
                    critical_missing_count=None,
                    ready_for_ai_core=None,
                    ready_for_ai=None,
                    detected_doc_type=None,
                    extractor_name=None,
                )
            )
            continue
        content = p.read_bytes()
        ext = p.suffix.lower().lstrip(".")
        for engine in engines:
            result = _run_engine(
                engine=engine,
                content=content,
                ext=ext,
                case_path=str(p),
                doc_type=case.doc_type,
                dpi=args.ocr_dpi,
                lang=args.ocr_lang,
            )
            results.append(result)
            status = "OK" if result.ok else "ERR"
            print(
                f"[{status}] {engine:<10} {p.name} "
                f"ms={result.elapsed_ms} core={result.ready_for_ai_core} "
                f"missing={result.critical_missing_count}"
            )

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    _write_reports(results, out_json, out_md)
    print(f"\nReport JSON: {out_json}")
    print(f"Report MD:   {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
