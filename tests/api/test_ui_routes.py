"""Tests for public UI pages."""

from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_trust_center_renders_security_positioning(client):
    resp = await client.get("/trust")

    assert resp.status_code == 200
    assert "Trust Center" in resp.text
    assert "Preuve DPO" in resp.text
    assert "Fernet" in resp.text
    assert "AES-256" not in resp.text


@pytest.mark.anyio
async def test_landing_links_to_trust_center(client):
    resp = await client.get("/")

    assert resp.status_code == 200
    assert 'href="/trust"' in resp.text
    assert "Télécharger la preuve DPO" in resp.text
