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
    assert "AI Security" in resp.text and "Control Tower" in resp.text
    # Metric tiles
    for tile in ("c-prompts", "c-responses", "c-redactions", "c-blocks", "c-critical"):
        assert f'id="{tile}"' in resp.text
    # Control-tower modules: AI flow, risk ring, event stream, audit timeline
    assert 'id="n-fwout"' in resp.text  # firewall response node in the AI flow
    assert 'id="ring-prog"' in resp.text  # risk posture ring
    assert 'id="events"' in resp.text
    assert 'id="timeline"' in resp.text
    # Demo orchestration
    assert 'id="demo-btn"' in resp.text
    assert "Lancer la démonstration" in resp.text
    # Premium assets are externalised (CSP-friendly, no inline handlers)
    assert "/static/css/firewall.css" in resp.text
    assert "/static/js/firewall.js" in resp.text
    assert "fonts.googleapis.com" in resp.text
    assert "onclick=" not in resp.text


@pytest.mark.anyio
async def test_service_worker_is_network_first_for_navigations(client):
    """The SW must not serve stale HTML after a deploy (no cached dashboards)."""
    resp = await client.get("/static/sw.js")

    assert resp.status_code == 200
    # Cache bumped so old stale-while-revalidate caches are purged on activate.
    assert "confidoc-v5" in resp.text
    # Navigations go to the network first.
    assert "isNavigation" in resp.text
    assert "fetch(req).catch(() => caches.match(req))" in resp.text


@pytest.mark.anyio
async def test_console_uses_premium_fonts_and_dark_default(client):
    """The console is aligned with the Control Tower: premium fonts + dark default."""
    page = await client.get("/ui")
    assert page.status_code == 200
    assert "Hanken+Grotesk" in page.text
    assert "Fraunces" in page.text
    assert "7c74ff" not in page.text  # legacy purple favicon removed

    js = await client.get("/static/js/app.js")
    assert js.status_code == 200
    # Dark is the default; OS light preference no longer auto-forces the light theme.
    assert "prefers-color-scheme: light" not in js.text
