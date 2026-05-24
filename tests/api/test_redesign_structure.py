"""Tests asserting the redesign structural elements are present.

These tests are gates for the dashboard redesign. They verify the
modular CSS files exist, expose the narrative-color tokens, the
component primitives, the signature elements (token-card, Trust Gauge,
Hero Literary, Scan Reveal, Privacy Lens), and that the main UI shell
exposes the new navigation, topbar shortcuts, document-list segments,
and document-detail layout.
"""

from __future__ import annotations

import re

import pytest

# --- Phase 1 · Tokens & primitives ---------------------------------------------


def _last_css_var(css: str, name: str) -> str:
    matches = re.findall(rf"{re.escape(name)}\s*:\s*([^;]+);", css)
    return matches[-1].strip() if matches else ""


@pytest.mark.anyio
async def test_ui_uses_new_design_tokens(client):
    resp = await client.get("/static/css/tokens.css")
    assert resp.status_code == 200
    css = resp.text
    # Narrative color tokens from spec §3.1
    assert "--accent: #047857" in css
    assert "--raw: #A4471E" in css
    assert "--surface: #FAFAF7" in css
    assert "--ink: #0F0F12" in css
    # The legacy --grad-brand token is bridged to the new accent (no longer
    # the indigo→violet gradient). Either it is absent, or it aliases the
    # new accent — in both cases the old purple gradient is gone.
    if "--grad-brand" in css:
        assert "#6366f1" not in css, "legacy indigo brand value still present"
        assert "#a855f7" not in css, "legacy violet brand value still present"


@pytest.mark.anyio
async def test_style_css_runtime_bridge_wins_after_legacy_tokens(client):
    resp = await client.get("/static/css/style.css")
    assert resp.status_code == 200
    css = resp.text
    assert css.rfind("FINAL REDESIGN TOKEN BRIDGE") > css.rfind(
        "linear-gradient(135deg, #6366f1"
    )
    assert _last_css_var(css, "--grad-brand") == "var(--accent)"
    assert _last_css_var(css, "--glass") == "none"
    assert _last_css_var(css, "--accent") == "#047857"
    assert _last_css_var(css, "--raw") == "#A4471E"


@pytest.mark.anyio
async def test_base_loads_signature_fonts(client):
    resp = await client.get("/static/css/base.css")
    assert resp.status_code == 200
    css = resp.text
    assert "'JetBrains Mono'" in css
    assert "Iowan Old Style" in css
    assert "font-variant-numeric: tabular-nums" in css


@pytest.mark.anyio
async def test_index_preconnects_jetbrains_mono(client):
    resp = await client.get("/ui")
    assert "fonts.googleapis.com" in resp.text
    assert "JetBrains+Mono" in resp.text or "JetBrains Mono" in resp.text


@pytest.mark.anyio
async def test_components_css_defines_primitives(client):
    resp = await client.get("/static/css/components.css")
    assert resp.status_code == 200
    css = resp.text
    for selector in [".btn-primary", ".btn-ghost", ".pill", ".chip", ".segment"]:
        assert selector in css, f"missing {selector}"


@pytest.mark.anyio
async def test_components_css_defines_layout_pieces(client):
    resp = await client.get("/static/css/components.css")
    css = resp.text
    for selector in [".card", ".kpi-card", ".input", ".table", ".nav-item"]:
        assert selector in css, f"missing {selector}"


# --- Phase 2 · Signature layer -------------------------------------------------

@pytest.mark.anyio
async def test_signatures_define_token_card(client):
    resp = await client.get("/static/css/signatures.css")
    assert resp.status_code == 200
    css = resp.text
    assert ".token-card" in css
    assert "JetBrains Mono" in css
    assert "linear-gradient" in css


@pytest.mark.anyio
async def test_signatures_define_hero_literary(client):
    resp = await client.get("/static/css/signatures.css")
    css = resp.text
    assert ".hero-literary" in css
    assert "font-style: italic" in css


@pytest.mark.anyio
async def test_signature_components_modules_exist(client):
    for name in ("trust-gauge", "scan-reveal", "privacy-lens", "command-palette", "drawer"):
        resp = await client.get(f"/static/js/components/{name}.js")
        assert resp.status_code == 200, f"missing component module {name}"


@pytest.mark.anyio
async def test_privacy_lens_uses_safe_dom_rendering(client):
    resp = await client.get("/static/js/components/privacy-lens.js")
    assert resp.status_code == 200
    js = resp.text
    assert "document.createElement" in js
    assert "textContent" in js
    assert "container.innerHTML = zones.map" not in js


# --- Phase 3 · Navigation ------------------------------------------------------

@pytest.mark.anyio
async def test_sidebar_groups_nav_into_three_zones(client):
    resp = await client.get("/ui")
    html = resp.text
    for label in ["Workspace", "Confiance", "Système"]:
        assert label in html, f"missing group label {label!r}"
    for nav in ["home", "documents", "clients", "quality", "audit", "settings"]:
        assert f'data-nav="{nav}"' in html, f"missing nav destination {nav}"
    assert 'data-nav="compliance"' not in html


@pytest.mark.anyio
async def test_topbar_has_search_and_copilot_hints(client):
    resp = await client.get("/ui")
    html = resp.text
    assert "⌘K" in html
    assert "⌘J" in html


@pytest.mark.anyio
async def test_redesign_actions_are_wired_in_app_js(client):
    resp = await client.get("/static/js/app.js")
    assert resp.status_code == 200
    js = resp.text
    for action in ("open-upload", "open-batch-upload", "open-copilot", "open-original"):
        assert f'action === "{action}"' in js
    assert "renderDocumentDetailShell" in js
    assert "openAnonReviewForCurrentDocument" in js


# --- Phase 4 · Documents list --------------------------------------------------

@pytest.mark.anyio
async def test_documents_panel_uses_segments_and_filters(client):
    resp = await client.get("/ui")
    html = resp.text
    for seg in ["seg-all", "seg-review", "seg-anon", "seg-draft", "seg-exported"]:
        assert f'data-segment="{seg}"' in html, f"missing segment {seg}"
    for chip in ["filter-dossier", "filter-type", "filter-trust", "filter-date"]:
        assert f'data-filter="{chip}"' in html, f"missing filter {chip}"
    assert 'data-col="trust"' in html


# --- Phase 5 · Document detail -------------------------------------------------

@pytest.mark.anyio
async def test_document_detail_layout_three_columns(client):
    resp = await client.get("/ui")
    html = resp.text
    assert "data-document-detail" in html
    assert "pane-original" in html
    assert "pane-anonymized" in html
    assert "rail-trust" in html
    assert "rail-copilot" in html
    assert "rail-audit" in html
    assert "data-privacy-lens-toggle" in html
    assert "⌘↵" in html or "⌘ ↵" in html or "Cmd+↵" in html


# --- Phase 6 · Accueil ---------------------------------------------------------

@pytest.mark.anyio
async def test_accueil_uses_hero_literary(client):
    resp = await client.get("/ui")
    html = resp.text
    assert 'class="hero-literary"' in html
    assert 'id="home-priority-list"' in html
    assert 'id="home-timeline"' in html
    assert 'id="home-kpis"' in html


@pytest.mark.anyio
async def test_home_briefing_renderer_is_wired(client):
    """Spec §5.1 — the Accueil briefing must be populated by renderHomeBriefing
    whenever the dashboard data lands. Without this hook, the hero literary
    line stays frozen on its '—' placeholders."""
    resp = await client.get("/static/js/app.js")
    assert resp.status_code == 200
    js = resp.text
    assert "function renderHomeBriefing" in js
    assert "renderHomeBriefing(data, summary, dossier360)" in js
    assert 'home-priority-count' in js
    assert 'home-priority-list' in js
    assert 'home-timeline' in js
    assert 'home-kpis' in js
