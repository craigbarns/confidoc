"""Tests for public lead capture endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def _payload() -> dict[str, object]:
    return {
        "email": "dpo@cabinet.fr",
        "full_name": "Marie Martin",
        "company": "Cabinet Martin",
        "role": "Associee",
        "team_size": "6-20",
        "document_volume": "51-250",
        "use_case": "Nous voulons anonymiser des bilans clients avant analyse IA.",
        "consent_to_contact": True,
    }


@pytest.mark.anyio
async def test_beta_lead_endpoint_requires_no_auth(client):
    with (
        patch("app.api.v1.leads._check_beta_lead_rate_limit", new_callable=AsyncMock),
        patch("app.api.v1.leads._persist_beta_lead", new_callable=AsyncMock) as persist,
        patch(
            "app.api.v1.leads.send_beta_lead_notification",
            new_callable=AsyncMock,
        ) as notify,
        patch(
            "app.api.v1.leads.send_beta_welcome_email",
            new_callable=AsyncMock,
        ) as welcome,
    ):
        persist.return_value = True
        notify.return_value = True
        welcome.return_value = True
        resp = await client.post("/api/v1/leads/beta", json=_payload())

    assert resp.status_code == 201
    assert resp.json()["status"] == "received"
    persist.assert_awaited_once()
    notify.assert_awaited_once()
    welcome.assert_awaited_once()


@pytest.mark.anyio
async def test_beta_lead_rejects_invalid_email(client):
    payload = _payload()
    payload["email"] = "not-an-email"

    resp = await client.post("/api/v1/leads/beta", json=payload)

    assert resp.status_code == 422


@pytest.mark.anyio
async def test_beta_lead_requires_contact_consent(client):
    payload = _payload()
    payload["consent_to_contact"] = False

    resp = await client.post("/api/v1/leads/beta", json=payload)

    assert resp.status_code == 422
