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
    assert '<meta property="og:title"' in resp.text
    assert "confidoc-og-card.png" in resp.text
    assert "🔒" not in resp.text


@pytest.mark.anyio
async def test_landing_links_to_trust_center(client):
    resp = await client.get("/")

    assert resp.status_code == 200
    assert 'href="/trust"' in resp.text
    assert "Télécharger la preuve DPO" in resp.text
    assert 'id="beta-form"' in resp.text
    assert 'id="pilot-proof"' in resp.text
    assert '<meta property="og:title"' in resp.text
    assert 'name="twitter:card" content="summary_large_image"' in resp.text
    assert "/api/v1/leads/beta" in resp.text


@pytest.mark.anyio
async def test_console_ui_shell_stays_self_hosted_and_well_formed(client):
    resp = await client.get("/ui")

    assert resp.status_code == 200
    assert resp.text.count('<main id="main-content"') == 1
    assert resp.text.count("</main>") == 1
    assert "translate.google.com" not in resp.text
    assert "google_translate_element" not in resp.text
