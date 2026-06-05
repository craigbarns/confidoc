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
    assert 'href="mailto:contact@confidoc.io"' not in resp.text
    assert 'href="#beta-access" class="btn-ghost">Contacter l\'équipe' in resp.text
    assert "consent_to_contact: true" in resp.text
    assert "landing_contact_cta" in resp.text


@pytest.mark.anyio
async def test_architecture_page_controls_are_csp_safe(client):
    resp = await client.get("/architecture")

    assert resp.status_code == 200
    assert "Architecture & Diagnostics" in resp.text
    assert "onclick=" not in resp.text
    assert "oninput=" not in resp.text
    assert 'data-tab="cartographie"' in resp.text
    assert 'data-tab="api-explorer"' in resp.text
    assert 'data-filter-tag="all"' in resp.text
    assert 'data-route-index="${idx}"' in resp.text
    assert "addEventListener('click'" in resp.text
    assert "addEventListener('input'" in resp.text


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
    assert "Déposez une pièce client" in resp.text
    assert "ConfiDoc masque les données sensibles avant l'analyse ou l'export." in resp.text
    assert 'id="btn-work-clients"' in resp.text
    assert 'data-action="open-clients"' in resp.text
    assert 'id="upload-zone"' in resp.text
    assert 'class="upload-zone-inner"' in resp.text
    assert 'id="upload-client-name"' in resp.text
    assert 'for="upload-client-name"' in resp.text
    assert "Document prêt pour vos questions" in resp.text
    assert (
        "Les données sensibles sont masquées. Vous pouvez poser vos questions en sécurité."
        in resp.text
    )
    assert "Résumer le document" in resp.text
    assert "Document prêt pour vos questions" in resp.text
    assert "Preuve RGPD" in resp.text
    assert 'id="btn-context-proof"' in resp.text
    assert (
        'href="/trust" target="_blank" rel="noopener" class="btn btn-ghost btn-sm">Preuve RGPD'
        not in resp.text
    )
    assert (
        'href="/trust" target="_blank" rel="noopener" class="btn btn-ghost btn-sm">Preuve DPO'
        not in resp.text
    )
    assert "Score RGPD non disponible" in resp.text
    assert "Ajoutez un premier document pour calculer votre posture RGPD." in resp.text
    assert "Aucune recommandation pour le moment." in resp.text

    js = await client.get("/static/js/app.js")
    assert js.status_code == 200
    assert "Télécharger la preuve RGPD" in js.text
    assert "downloadAuditReport();" in js.text


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


@pytest.mark.anyio
async def test_home_secondary_content_is_progressively_disclosed(client):
    """Accueil: dense secondary blocks are collapsed behind <details> (less noise)."""
    resp = await client.get("/ui")
    assert resp.status_code == 200
    # Secondary dashboard sections are hidden/collapsed; primary upload stays first.
    assert resp.text.count("home-advanced") >= 2
    assert "Déposez une pièce client" in resp.text
    assert "Tableau de bord détaillé" in resp.text
    assert "/static/css/workspace.css" in resp.text
    # Jargon removed.
    assert "Cockpit cabinet" not in resp.text
    assert "Dossier 360" not in resp.text
    # Functionality preserved: the upload zone + JS-driven ids still present.
    assert 'id="std-upload-zone"' in resp.text
    assert 'id="dash-activity-chart"' in resp.text


@pytest.mark.anyio
async def test_document_analysis_advanced_blocks_are_collapsed(client):
    """Analyse IA: advanced config + technical KPIs collapse; chat stays primary."""
    resp = await client.get("/ui")
    assert resp.status_code == 200
    # Document-analysis collapsibles add to the home ones.
    assert resp.text.count("home-advanced") >= 4
    assert 'class="home-advanced expert-only"' in resp.text
    assert "Outils cabinet" in resp.text
    assert "Détails techniques du document" in resp.text
    # Primary analysis surface + advanced controls remain in the DOM (JS intact).
    assert 'id="chat-messages"' in resp.text
    assert 'id="cabinet-doc-type"' in resp.text
    assert 'id="kpi-next-action"' in resp.text


@pytest.mark.anyio
async def test_ui_is_de_jargonised(client):
    """Technical jargon is replaced by plain, reassuring wording across /ui."""
    resp = await client.get("/ui")
    assert resp.status_code == 200
    for jargon in (
        "Data Flywheel",
        "Pilotage Qualité",
        "Distribution des Ajustements",
        "pipeline de production",
        "Trust score",
        "Golden sets",
        "Audit-Ready",
        "Copilot: OFF",
        "Mode rapport: OFF",
        "À reviewer",
        "Reviewer",
    ):
        assert jargon not in resp.text, jargon
    for plain in (
        "Apprentissage continu",
        "Indice de confiance",
        "Preuve RGPD détaillée",
        "Répartition des risques",
        "Pièces client",
        "Questions sur le document",
    ):
        assert plain in resp.text, plain
    # "Grand livre" survives only as the accounting document type, never as a UI title.
    assert "Grand livre d'audit" not in resp.text


@pytest.mark.anyio
async def test_quality_and_compliance_analytics_are_collapsed(client):
    """Qualité/Conformité: dense analytics collapse, keeping the score primary."""
    resp = await client.get("/ui")
    assert resp.status_code == 200
    assert resp.text.count("home-advanced") >= 6
    assert 'class="home-advanced expert-only"' in resp.text
    assert "Détails : apprentissage & traitement" in resp.text
    assert "Détails de conformité" in resp.text
    # JS-driven analytics still in the DOM.
    assert 'id="dash-risk-chart"' in resp.text
    assert 'id="audit-ledger-tbody"' in resp.text
    assert 'id="quality-status-summary-grid"' in resp.text


@pytest.mark.anyio
async def test_audit_panel_stays_simple_and_document_oriented(client):
    resp = await client.get("/ui")
    assert resp.status_code == 200
    assert "Preuves RGPD" in resp.text
    assert "La preuve se télécharge depuis chaque document validé." in resp.text
    assert 'data-action="open-documents"' in resp.text
    assert 'id="audit-resource-filter"' not in resp.text
    assert 'id="btn-audit-refresh"' not in resp.text
    assert "Le journal d'audit s'affichera ici. Branchement API à venir." not in resp.text


@pytest.mark.anyio
async def test_platform_navigation_links_ui_and_firewall(client):
    """One platform: /ui keeps advanced AI protection reachable from the header."""
    ui = await client.get("/ui")
    assert ui.status_code == 200
    assert "topbar__firewall-link expert-only" in ui.text
    assert 'href="/firewall"' in ui.text
    assert "fw-badge" in ui.text  # the Active badge

    fw = await client.get("/firewall")
    assert fw.status_code == 200
    assert 'class="nav-back"' in fw.text
    assert 'href="/ui"' in fw.text
    assert "← ConfiDoc" in fw.text


@pytest.mark.anyio
async def test_home_uses_loaded_fonts_and_emerald_accent(client):
    """Accueil polish: loaded fonts only, emerald hero, clean greeting/label."""
    resp = await client.get("/ui")
    assert resp.status_code == 200
    # The unloaded 'Outfit' font is gone everywhere (it always fell back to system).
    assert "'Outfit'" not in resp.text
    # Hero upload is emerald, not the legacy indigo/purple.
    assert "124, 116, 255" not in resp.text and "124,116,255" not in resp.text
    # Clean greeting (no permanent "Collaborateur" placeholder) + softer label.
    assert ">Collaborateur<" not in resp.text
    assert "Nom du client" in resp.text
    assert "(Obligatoire)" not in resp.text
