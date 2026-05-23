from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.v1 import _privacy_gate


@pytest.mark.asyncio
async def test_require_privacy_gate_returns_allowed_result(monkeypatch) -> None:
    document = SimpleNamespace(id=uuid.uuid4())

    async def fake_evaluate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"decision": "allow", "warnings": ["audit trace conservée"]}

    monkeypatch.setattr(_privacy_gate, "evaluate_document_privacy_gate", fake_evaluate)

    result = await _privacy_gate.require_privacy_gate(
        SimpleNamespace(),
        document,
        "external_ai",
        anonymized_text="[CLIENT_1]",
    )

    assert result["decision"] == "allow"


@pytest.mark.asyncio
async def test_require_privacy_gate_blocks_human_review_required(monkeypatch) -> None:
    document = SimpleNamespace(id=uuid.uuid4())

    async def fake_evaluate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "decision": "human_review_required",
            "reasons": ["Risque élevé sans validation humaine DPO."],
            "required_actions": ["Valider manuellement les mappings."],
        }

    monkeypatch.setattr(_privacy_gate, "evaluate_document_privacy_gate", fake_evaluate)

    with pytest.raises(HTTPException) as exc_info:
        await _privacy_gate.require_privacy_gate(
            SimpleNamespace(),
            document,
            "external_ai",
            anonymized_text="[CLIENT_1]",
        )

    assert exc_info.value.status_code == 400
    assert "Privacy Gate DPO: human_review_required" in exc_info.value.detail
