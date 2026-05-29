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
    main_start = resp.text.index('<main id="main-content"')
    main_end = resp.text.index("</main>", main_start)
    panel_ai = resp.text.index('<div id="panel-ai"', main_start)
    assert main_start < panel_ai < main_end
    assert "translate.google.com" not in resp.text
    assert "google_translate_element" not in resp.text
    assert "onclick=" not in resp.text
    assert "oninput=" not in resp.text
    assert "Accueil cabinet" in resp.text
    assert 'id="btn-work-clients"' in resp.text
    assert 'data-action="open-clients"' in resp.text
    assert 'id="upload-zone"' in resp.text
    assert 'class="upload-zone-inner"' in resp.text
    assert 'id="upload-client-name"' in resp.text
    assert 'for="upload-client-name"' in resp.text
    assert "Document prêt pour l’analyse IA" in resp.text
    assert "Le document a été anonymisé. Vous pouvez poser vos questions en toute sécurité." in resp.text
    assert "Résumer le document" in resp.text
    assert "Document anonymisé et prêt pour l’IA" in resp.text
    assert "Score RGPD non disponible" in resp.text
    assert "Ajoutez un premier document pour calculer votre posture RGPD." in resp.text
    assert "Aucune recommandation pour le moment." in resp.text


@pytest.mark.anyio
async def test_firewall_dashboard_renders(client):
    resp = await client.get("/firewall")

    assert resp.status_code == 200
    # Headline positioning
    assert "Tous les échanges IA sont inspectés en temps réel" in resp.text
    assert "AI" in resp.text and "Firewall" in resp.text
    # Counter tiles
    assert 'id="c-prompts"' in resp.text
    assert 'id="c-responses"' in resp.text
    assert 'id="c-redactions"' in resp.text
    assert 'id="c-blocks"' in resp.text
    assert 'id="c-critical"' in resp.text
    # Demo CTA + journey + events
    assert 'id="demo-btn"' in resp.text
    assert "Charger une démo" in resp.text
    assert "Fuite interceptée" in resp.text
    assert 'id="events"' in resp.text
    # Uses the public stats + demo endpoints, no inline event handlers
    assert "/api/v1/firewall/stats" in resp.text
    assert "/api/v1/firewall/demo" in resp.text
    assert "onclick=" not in resp.text
