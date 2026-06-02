import httpx
import pytest

from app.services import review_agent


def test_llm_429_is_user_friendly() -> None:
    response = httpx.Response(
        429,
        headers={"retry-after": "45"},
        request=httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions"),
    )

    with pytest.raises(review_agent.ReviewAgentTransientError) as exc_info:
        review_agent._raise_for_llm_status(response)

    exc = exc_info.value
    assert exc.code == "mistral_rate_limited"
    assert exc.retry_after_seconds == 45
    assert "https://api.mistral.ai" not in str(exc)
    assert "Too Many Requests" not in str(exc)


@pytest.mark.asyncio
async def test_streaming_review_degrades_when_llm_is_rate_limited(monkeypatch) -> None:
    async def rate_limited_call(*_args, **_kwargs) -> str:
        raise review_agent.ReviewAgentTransientError(
            "Mistral limite temporairement les analyses.",
            code="mistral_rate_limited",
            retry_after_seconds=45,
        )

    from unittest.mock import patch

    with patch("app.services.review.llm.llm_call", side_effect=rate_limited_call):
        review_agent._reset_graph()

        events = [
            event
            async for event in review_agent.run_review_streaming(
                "Contrat anonymise entre CLIENT_1 et CLIENT_2.",
                {"PERSON": 2},
            )
        ]

    assert events[-1]["status"] == "complete"
    assert not any(event["status"] == "error" for event in events)

    synthesize_events = [
        event for event in events if event["step"] == "synthesize" and event["status"] == "done"
    ]
    assert synthesize_events
    payload = synthesize_events[-1]["data"]
    assert payload["degraded"] is True
    assert payload["error_code"] == "mistral_rate_limited"
    assert payload["verdict"] == "reserve"
    assert payload["review_note"]
    assert "https://api.mistral.ai" not in payload["error"]
