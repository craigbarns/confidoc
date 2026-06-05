#!/usr/bin/env python3
"""Railway smoke test for ConfiDoc.

Checks public operational endpoints and, when demo credentials are supplied,
performs a login, uploads a synthetic document and fetches its score.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

SYNTHETIC_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
    b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 108>>stream\n"
    b"BT /F1 12 Tf 72 760 Td "
    b"(ConfiDoc smoke test - document synthetique sans donnees reelles.) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"xref\n"
    b"0 6\n"
    b"0000000000 65535 f\n"
    b"0000000009 00000 n\n"
    b"0000000058 00000 n\n"
    b"0000000115 00000 n\n"
    b"0000000233 00000 n\n"
    b"0000000391 00000 n\n"
    b"trailer<</Root 1 0 R/Size 6>>\n"
    b"startxref\n"
    b"461\n"
    b"%%EOF\n"
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    body: bytes | None = None,
    content_type: str | None = "application/json",
    timeout: float = 15.0,
) -> tuple[int, dict[str, Any]]:
    headers: dict[str, str] = {"User-Agent": "confidoc-smoke-test/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if content_type and body is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(
        _url(base_url, path),
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(payload or "{}")
            except json.JSONDecodeError:
                parsed = {"raw": payload[:300]}
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(payload or "{}")
        except json.JSONDecodeError:
            parsed = {"detail": payload[:300]}
        return exc.code, parsed


def request_bytes(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict[str, str], bytes]:
    headers: dict[str, str] = {"User-Agent": "confidoc-smoke-test/1.0"}
    if content_type and body is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(
        _url(base_url, path),
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def multipart_upload_body(
    *,
    field_name: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = f"----ConfiDocSmoke{int(time.time() * 1000)}"
    chunks = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        ).encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def check_endpoint(base_url: str, path: str, expected_statuses: set[int]) -> CheckResult:
    status, payload = request_json(base_url, path)
    ok = status in expected_statuses
    detail = payload.get("status") or payload.get("service") or payload.get("version") or status
    return CheckResult(path, ok, f"HTTP {status} · {detail}")


def check_public_page(
    base_url: str,
    path: str,
    *,
    label: str,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
) -> CheckResult:
    status, headers, content = request_bytes(base_url, path)
    text = content.decode("utf-8", errors="replace")
    missing = [item for item in required if item not in text]
    present_forbidden = [item for item in forbidden if item in text]
    is_html = "text/html" in str(headers.get("Content-Type") or headers.get("content-type") or "")
    ok = status == 200 and is_html and not missing and not present_forbidden
    detail = f"HTTP {status} · html={is_html}"
    if missing:
        detail += f" · missing={missing}"
    if present_forbidden:
        detail += f" · forbidden={present_forbidden}"
    return CheckResult(label, ok, detail)


def check_public_pdf(base_url: str, path: str, *, label: str) -> CheckResult:
    status, headers, content = request_bytes(base_url, path)
    content_type = str(headers.get("Content-Type") or headers.get("content-type") or "")
    ok = status == 200 and content_type.startswith("application/pdf") and len(content) > 1000
    return CheckResult(
        label,
        ok,
        f"HTTP {status} · content_type={content_type} · size={len(content)}",
    )


def check_firewall_stats(base_url: str) -> CheckResult:
    status, payload = request_json(base_url, "/api/v1/firewall/stats")
    firewall = payload.get("firewall") if isinstance(payload, dict) else {}
    counters = payload.get("counters") if isinstance(payload, dict) else {}
    ok = (
        status == 200
        and isinstance(firewall, dict)
        and firewall.get("enabled") is True
        and isinstance(counters, dict)
        and counters.get("available") is True
    )
    return CheckResult(
        "firewall stats",
        ok,
        (
            f"HTTP {status} · enabled={firewall.get('enabled')} "
            f"· mode={firewall.get('mode')} · counters={counters.get('available')}"
        ),
    )


def check_firewall_demo(base_url: str) -> CheckResult:
    status, payload = request_json(
        base_url,
        "/api/v1/firewall/demo",
        method="POST",
        content_type=None,
    )
    steps = payload.get("steps") if isinstance(payload, dict) else []
    verdicts = [
        ((step.get("firewall") or {}).get("verdict") if isinstance(step, dict) else None)
        for step in steps
        if isinstance(step, dict)
    ]
    outputs = [str(step.get("output") or "") for step in steps if isinstance(step, dict)]
    ok = (
        status == 200
        and {"allow", "redact", "block"}.issubset(set(verdicts))
        and any("[EMAIL]" in output for output in outputs)
        and any("bloqu" in output.lower() for output in outputs)
    )
    return CheckResult(
        "firewall live demo",
        ok,
        f"HTTP {status} · verdicts={verdicts}",
    )


def login(base_url: str, email: str, password: str) -> tuple[CheckResult, str | None]:
    body = json.dumps({"email": email, "password": password}).encode("utf-8")
    status, payload = request_json(base_url, "/api/v1/auth/login", method="POST", body=body)
    token = payload.get("access_token") if isinstance(payload, dict) else None
    return (
        CheckResult(
            "login demo",
            status == 200 and bool(token),
            f"HTTP {status} · {'token received' if token else payload.get('detail', 'no token')}",
        ),
        str(token) if token else None,
    )


def upload_synthetic(base_url: str, token: str) -> tuple[CheckResult, str | None]:
    query = urllib.parse.urlencode(
        {
            "auto_anonymize": "false",
            "client_name": "Smoke Test Demo",
            "document_type": "auto",
            "profile": "strict",
        }
    )
    body, content_type = multipart_upload_body(
        field_name="file",
        filename="confidoc_smoke_demo.pdf",
        content=SYNTHETIC_PDF,
        content_type="application/pdf",
    )
    status, payload = request_json(
        base_url,
        f"/api/v1/uploads?{query}",
        method="POST",
        token=token,
        body=body,
        content_type=content_type,
        timeout=30.0,
    )
    doc_id = payload.get("document_id") if isinstance(payload, dict) else None
    return (
        CheckResult(
            "upload synthetic document",
            status == 201 and bool(doc_id),
            f"HTTP {status} · {doc_id or payload.get('detail', 'no document_id')}",
        ),
        str(doc_id) if doc_id else None,
    )


def fetch_score(base_url: str, token: str, document_id: str) -> CheckResult:
    status, payload = request_json(
        base_url,
        f"/api/v1/documents/{document_id}/risk-score",
        token=token,
    )
    score = payload.get("risk_score") if isinstance(payload, dict) else None
    return CheckResult(
        "risk score",
        status == 200 and score is not None,
        f"HTTP {status} · risk_score={score if score is not None else 'n/a'}",
    )


def fetch_json_path(
    base_url: str,
    path: str,
    *,
    token: str | None = None,
    label: str,
    required_key: str | None = None,
) -> CheckResult:
    status, payload = request_json(base_url, path, token=token)
    ok = status == 200 and (required_key is None or payload.get(required_key) is not None)
    detail_value = payload.get(required_key) if required_key else payload.get("status", "ok")
    return CheckResult(label, ok, f"HTTP {status} · {required_key or 'status'}={detail_value}")


def trigger_demo(base_url: str, token: str) -> tuple[CheckResult, str | None]:
    status, payload = request_json(
        base_url,
        "/api/v1/demo",
        method="POST",
        token=token,
    )
    doc_id = payload.get("document_id") if isinstance(payload, dict) else None
    return (
        CheckResult(
            "trigger demo endpoint",
            status == 201 and bool(doc_id),
            f"HTTP {status} · {doc_id or payload.get('detail', 'no document_id')}",
        ),
        str(doc_id) if doc_id else None,
    )


def trigger_public_investor_demo(base_url: str) -> tuple[CheckResult, dict[str, Any]]:
    status, payload = request_json(
        base_url,
        "/api/v1/demo/investor-document",
        method="POST",
        content_type=None,
    )
    doc_id = payload.get("document_id") if isinstance(payload, dict) else None
    urls = payload.get("urls") if isinstance(payload, dict) else None
    return (
        CheckResult(
            "public investor demo",
            status == 201 and bool(doc_id) and isinstance(urls, dict),
            f"HTTP {status} · {doc_id or payload.get('detail', 'no document_id')}",
        ),
        payload if isinstance(payload, dict) else {},
    )


def fetch_raw_path(
    base_url: str,
    path: str,
    *,
    token: str | None = None,
    label: str = "raw endpoint",
) -> CheckResult:
    import urllib.request

    headers = {"User-Agent": "confidoc-smoke-test/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        _url(base_url, path),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            status = resp.status
            content_type = resp.headers.get("content-type", "")
            disposition = resp.headers.get("content-disposition", "")
            content = resp.read()
            previewable = content_type.startswith("application/pdf") or content_type.startswith(
                "image/"
            )
            inline = "inline" in disposition.lower()
            ok = status == 200 and len(content) > 0 and previewable and inline
            return CheckResult(
                label,
                ok,
                (
                    f"HTTP {status} · content_type={content_type} "
                    f"· disposition={disposition} · size={len(content)}"
                ),
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return CheckResult(label, False, f"HTTP {exc.code} · {detail or exc.reason}")
    except Exception as exc:
        return CheckResult(label, False, f"Error: {exc}")


def fetch_raw(base_url: str, token: str, document_id: str) -> CheckResult:
    return fetch_raw_path(
        base_url,
        f"/api/v1/documents/{document_id}/raw",
        token=token,
        label="raw endpoint",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="ConfiDoc Railway smoke test")
    parser.add_argument(
        "--base-url", default=os.getenv("CONFIDOC_BASE_URL", "http://localhost:8000")
    )
    parser.add_argument("--email", default=os.getenv("CONFIDOC_DEMO_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("CONFIDOC_DEMO_PASSWORD", ""))
    parser.add_argument("--no-upload", action="store_true", help="Skip authenticated upload")
    parser.add_argument(
        "--allow-degraded-readiness",
        action="store_true",
        help="Accept HTTP 503 on /readiness while still printing the degraded status.",
    )
    args = parser.parse_args()

    results = [
        check_endpoint(args.base_url, "/health", {200}),
        check_endpoint(args.base_url, "/version", {200}),
        check_endpoint(args.base_url, "/ui", {200}),
        check_endpoint(args.base_url, "/static/js/app.js", {200}),
        check_endpoint(args.base_url, "/static/css/style.css", {200}),
        check_endpoint(args.base_url, "/api/v1/demo/public", {200, 202}),
        check_endpoint(
            args.base_url,
            "/readiness",
            {200, 503} if args.allow_degraded_readiness else {200},
        ),
        check_public_page(
            args.base_url,
            "/",
            label="landing public promises",
            required=(
                'href="#demo-sandbox"',
                "Contacter l'équipe",
                "/api/v1/leads/beta",
                "consent_to_contact: true",
            ),
            forbidden=("mailto:contact@confidoc.io",),
        ),
        check_public_page(
            args.base_url,
            "/architecture",
            label="architecture interactions",
            required=(
                'data-tab="api-explorer"',
                'data-filter-tag="all"',
                "addEventListener('click'",
            ),
            forbidden=("onclick=", "oninput="),
        ),
        check_public_page(
            args.base_url,
            "/trust",
            label="trust center interactions",
            required=(
                "data-scorecard-toggle",
                'href="/#demo-sandbox"',
                "<script nonce=",
            ),
            forbidden=("onclick=", "oninput=", "/#demo-section"),
        ),
        check_public_page(
            args.base_url,
            "/firewall",
            label="firewall dashboard copy",
            required=(
                "Protection",
                "anti-fuite IA",
                "Prompt vérifié",
                "Réponse vérifiée",
                "/static/js/firewall.js",
            ),
            forbidden=("AI Security", "Control Tower", "onclick=", "oninput="),
        ),
        check_public_pdf(
            args.base_url,
            "/api/v1/demo/public/audit-report-pdf",
            label="public DPO proof PDF",
        ),
        check_firewall_stats(args.base_url),
        check_firewall_demo(args.base_url),
    ]

    token = None
    if args.email and args.password:
        login_result, token = login(args.base_url, args.email, args.password)
        results.append(login_result)
    else:
        results.append(CheckResult("login demo", True, "skipped: credentials not provided"))

    public_demo_result, public_demo_payload = trigger_public_investor_demo(args.base_url)
    results.append(public_demo_result)
    public_urls = public_demo_payload.get("urls") if isinstance(public_demo_payload, dict) else {}
    if isinstance(public_urls, dict):
        raw_path = public_urls.get("raw")
        score_path = public_urls.get("score")
        audit_path = public_urls.get("audit")
        export_path = public_urls.get("export")
        if raw_path:
            results.append(fetch_raw_path(args.base_url, raw_path, label="public demo raw"))
        if score_path:
            results.append(
                fetch_json_path(
                    args.base_url,
                    score_path,
                    label="public demo score",
                    required_key="risk_score",
                )
            )
        if audit_path:
            results.append(
                fetch_json_path(
                    args.base_url,
                    audit_path,
                    label="public demo audit",
                    required_key="total_actions",
                )
            )
        if export_path:
            results.append(
                fetch_json_path(
                    args.base_url,
                    export_path,
                    label="public demo export",
                )
            )

    if token and not args.no_upload:
        demo_result, demo_doc_id = trigger_demo(args.base_url, token)
        results.append(demo_result)
        if demo_doc_id:
            results.append(fetch_score(args.base_url, token, demo_doc_id))
            results.append(fetch_raw(args.base_url, token, demo_doc_id))

        upload_result, document_id = upload_synthetic(args.base_url, token)
        results.append(upload_result)
        if document_id:
            results.append(fetch_score(args.base_url, token, document_id))
    else:
        results.append(CheckResult("upload synthetic document", True, "skipped"))
        results.append(CheckResult("trigger demo endpoint", True, "skipped"))

    for item in results:
        marker = "OK" if item.ok else "FAIL"
        print(f"[{marker}] {item.name}: {item.detail}")

    return 0 if all(item.ok for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
