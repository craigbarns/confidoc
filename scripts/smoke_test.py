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


SYNTHETIC_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 108>>stream
BT /F1 12 Tf 72 760 Td (ConfiDoc smoke test - document synthetique sans donnees reelles.) Tj ET
endstream endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000233 00000 n
0000000391 00000 n
trailer<</Root 1 0 R/Size 6>>
startxref
461
%%EOF
"""


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
            return resp.status, json.loads(payload or "{}")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(payload or "{}")
        except json.JSONDecodeError:
            parsed = {"detail": payload[:300]}
        return exc.code, parsed


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
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
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


def main() -> int:
    parser = argparse.ArgumentParser(description="ConfiDoc Railway smoke test")
    parser.add_argument("--base-url", default=os.getenv("CONFIDOC_BASE_URL", "http://localhost:8000"))
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
        check_endpoint(
            args.base_url,
            "/readiness",
            {200, 503} if args.allow_degraded_readiness else {200},
        ),
    ]

    token = None
    if args.email and args.password:
        login_result, token = login(args.base_url, args.email, args.password)
        results.append(login_result)
    else:
        results.append(CheckResult("login demo", True, "skipped: credentials not provided"))

    if token and not args.no_upload:
        upload_result, document_id = upload_synthetic(args.base_url, token)
        results.append(upload_result)
        if document_id:
            results.append(fetch_score(args.base_url, token, document_id))
    else:
        results.append(CheckResult("upload synthetic document", True, "skipped"))

    for item in results:
        marker = "OK" if item.ok else "FAIL"
        print(f"[{marker}] {item.name}: {item.detail}")

    return 0 if all(item.ok for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
