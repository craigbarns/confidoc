"""Tests for the public demo service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services import demo_service


class _Risk:
    def to_dict(self) -> dict[str, object]:
        return {"score": 0.0, "level": "low", "signals": []}


@pytest.mark.asyncio
async def test_compute_demo_result_returns_public_payload(tmp_path):
    demo_pdf = tmp_path / "demo.pdf"
    demo_pdf.write_bytes(b"%PDF demo")

    detections = [
        {
            "entity_type": "email",
            "start_index": 0,
            "end_index": 7,
            "value_excerpt": "a@b.com",
            "replacement": "[EMAIL]",
        },
        {
            "entity_type": "person_name",
            "start_index": 8,
            "end_index": 19,
            "value_excerpt": "Jean Dupont",
            "replacement": "[PERSONNE_1]",
        },
    ]

    with (
        patch.object(demo_service, "DEMO_DOC_PATH", demo_pdf),
        patch.object(
            demo_service,
            "extract_text_from_file_with_meta",
            new=AsyncMock(
                return_value=(
                    "Jean Dupont a@b.com",
                    {"pages": 1, "method": "mistral_ocr", "model": "mistral-ocr-latest"},
                )
            ),
        ),
        patch.object(demo_service, "classify_document_type", return_value="generic"),
        patch.object(
            demo_service,
            "anonymize_text",
            return_value=("Email: [EMAIL]\nClient: [PERSONNE_1]", detections, object()),
        ),
        patch.object(demo_service, "analyze_reidentification_risk", return_value=_Risk()),
    ):
        result = await demo_service._compute_demo_result()

    assert result["status"] == "ready"
    assert result["filename"] == "demo.pdf"
    assert result["detections_count"] == 2
    assert result["entity_summary"] == {"EMAIL": 1, "PERSONNE": 1}
    assert result["risk"]["level"] == "low"
    assert result["extraction_method"] == "mistral_ocr"
    assert result["extraction_provider"] == "mistral"
    assert "[EMAIL]" in result["anonymized_excerpt"]
    assert result["proof"]["export_policy"]["label"] == "Export autorise"


def test_build_demo_audit_pdf_returns_pdf_bytes():
    payload = {
        "filename": "demo.pdf",
        "document_type": "generic",
        "pages": 1,
        "extraction_method": "pymupdf",
        "anonymized_excerpt": "Client: [PERSONNE_1]\nEmail: [EMAIL]",
        "detections_count": 2,
        "entity_summary": {"PERSONNE": 1, "EMAIL": 1},
        "risk": {
            "score": 0.0,
            "level": "low",
            "recommendation": "Anonymisation forte.",
            "signals": [],
        },
    }

    pdf = demo_service.build_demo_audit_pdf(payload)

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


@pytest.mark.asyncio
async def test_warm_demo_cache_uses_memory_when_redis_unavailable():
    demo_service._memory_demo_cache = None
    payload = {"status": "ready", "detections_count": 3}

    with (
        patch.object(demo_service, "_compute_demo_result", new=AsyncMock(return_value=payload)),
        patch.object(demo_service, "_get_redis", return_value=None),
    ):
        await demo_service.warm_demo_cache()

    assert await demo_service.get_demo_result() == payload
    demo_service._memory_demo_cache = None


@pytest.mark.asyncio
async def test_get_demo_result_falls_back_to_mock_payload_when_cache_unavailable():
    demo_service._memory_demo_cache = None

    with patch.object(demo_service, "_get_redis", return_value=None):
        result = await demo_service.get_demo_result()

    assert result is not None
    assert result["status"] == "ready"
    assert result["is_mock"] is True
    assert result["source"] == "mock_demo_fallback"
    demo_service._memory_demo_cache = None
