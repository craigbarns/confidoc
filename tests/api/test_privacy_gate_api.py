import pytest


def test_privacy_gate_route_registered() -> None:
    from app.api.v1.ai import router

    paths = [route.path for route in router.routes]
    assert "/privacy-gate/{document_id}" in paths


@pytest.mark.asyncio
async def test_privacy_gate_requires_auth(client) -> None:
    resp = await client.get("/api/v1/ai/privacy-gate/some-fake-uuid")
    assert resp.status_code == 401

