# ConfiDoc Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the "Sober Professional + signature" redesign (spec `docs/superpowers/specs/2026-05-23-confidoc-dashboard-redesign-design.md`) to the authenticated dashboard — new tokens, simplified navigation, unified workflows, and 5 signature elements (token-card, Trust Gauge, Hero Literary, Scan Reveal, Privacy Lens) — without changing the backend.

**Architecture:** Vanilla HTML + CSS + JS preserved. Split the monolithic `style.css` (5 695 lines) into thematic files. Move interactive signature components into ES module files under `app/static/js/components/`. Server-rendered Jinja-style templates updated incrementally so each task leaves the app in a working state. Existing API and Python services untouched.

**Tech Stack:** Python FastAPI + Jinja-style templates, Vanilla JS (no framework, no bundler) loaded via `<script type="module">`, CSS variables (custom properties), pytest for integration tests against rendered HTML, existing smoke tests for end-to-end coverage.

---

## File Structure (target state)

**Created**
- `app/static/css/tokens.css` — design tokens only (light + dark)
- `app/static/css/base.css` — reset, typography, fonts, skip link, prefers-reduced-motion
- `app/static/css/components.css` — Button, Pill, Chip, Segment, Card, Input, Table, NavItem
- `app/static/css/signatures.css` — token-card, TrustGauge styles, HeroLiterary styles, ScanReveal styles, PrivacyLens styles
- `app/static/css/screens.css` — per-screen layouts (Accueil, Documents, Detail, Dossiers, Qualité, Audit, Settings)
- `app/static/js/components/trust-gauge.js` — `<trust-gauge>` web component
- `app/static/js/components/scan-reveal.js` — `triggerScanReveal(rootEl)` overlay helper
- `app/static/js/components/privacy-lens.js` — toggle + heatmap overlay
- `app/static/js/components/command-palette.js` — ⌘K palette
- `app/static/js/components/drawer.js` — ⌘J Copilot drawer
- `tests/api/test_redesign_structure.py` — integration tests on rendered HTML
- `tests/static/test_trust_gauge.html` — JS unit test page for Trust Gauge
- `tests/static/test_scan_reveal.html` — JS unit test page for Scan Reveal

**Modified**
- `app/templates/index.html` — restructured (topbar, sidebar, panels)
- `app/static/css/style.css` — keep as the *imported* bundle (`@import` the new files in order), eventually shrunk to <3 000 lines
- `app/static/js/app.js` — keep but extract signature behaviors to component files; thin out

**Deleted (only after full migration)**
- Glassmorphism + indigo-violet gradient rules in `style.css`
- `--accent-glow`, `--grad-brand`, `--grad-surface`, `--grad-glow` tokens and their usages

---

## Phase 0 · Bootstrap

### Task 0.1: Snapshot baseline tests

**Files:**
- Read: `tests/api/test_ui_routes.py`

- [ ] **Step 1: Capture current passing smoke tests**

Run: `pytest tests/api/test_ui_routes.py -v --no-header 2>&1 | tee /tmp/redesign-baseline.txt`
Expected: all current tests PASS. Save the test names list — these must keep passing throughout the plan unless explicitly updated in a task.

- [ ] **Step 2: Confirm `/ui` endpoint renders**

Run: `curl -s -o /tmp/ui-before.html -w "%{http_code}\n" http://localhost:8000/ui` (start the dev server first if needed)
Expected: `200`. If 8000 is not running, run `uvicorn app.main:app --port 8000 &` first.

- [ ] **Step 3: Commit baseline note**

Create empty marker file:
```bash
mkdir -p docs/superpowers/notes
printf 'baseline captured %s\n' "$(date -u +%FT%TZ)" > docs/superpowers/notes/redesign-baseline.md
git add docs/superpowers/notes/redesign-baseline.md
git commit -m "chore(redesign): mark redesign baseline"
```

### Task 0.2: Create empty new CSS files imported in order

**Files:**
- Create: `app/static/css/tokens.css`, `app/static/css/base.css`, `app/static/css/components.css`, `app/static/css/signatures.css`, `app/static/css/screens.css`
- Modify: `app/static/css/style.css` (add imports at top)

- [ ] **Step 1: Create the 5 empty CSS files**

Each file gets only a header comment for now.

```bash
for f in tokens base components signatures screens; do
  printf '/* ConfiDoc — %s.css */\n' "$f" > "app/static/css/$f.css"
done
```

- [ ] **Step 2: Add `@import` lines at the very top of `style.css`**

Edit `app/static/css/style.css` — insert before line 1:

```css
@import "./tokens.css";
@import "./base.css";
@import "./components.css";
@import "./signatures.css";
@import "./screens.css";
/* Legacy content below — to be migrated and deleted */
```

- [ ] **Step 3: Verify the page still loads**

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/ui`
Expected: `200`.

- [ ] **Step 4: Commit**

```bash
git add app/static/css/
git commit -m "chore(redesign): scaffold modular CSS files"
```

### Task 0.3: Create empty JS component files and wire script tag

**Files:**
- Create: `app/static/js/components/trust-gauge.js`, `app/static/js/components/scan-reveal.js`, `app/static/js/components/privacy-lens.js`, `app/static/js/components/command-palette.js`, `app/static/js/components/drawer.js`
- Modify: `app/templates/index.html` (add module script tag near `</body>`)

- [ ] **Step 1: Create the 5 empty component files**

```bash
mkdir -p app/static/js/components
for f in trust-gauge scan-reveal privacy-lens command-palette drawer; do
  printf '// ConfiDoc — %s component\nexport function init_%s() {}\n' "$f" "${f//-/_}" > "app/static/js/components/$f.js"
done
```

- [ ] **Step 2: Add an entry module that imports them all**

Create `app/static/js/components/index.js`:

```js
import { init_trust_gauge } from "./trust-gauge.js";
import { init_scan_reveal } from "./scan-reveal.js";
import { init_privacy_lens } from "./privacy-lens.js";
import { init_command_palette } from "./command-palette.js";
import { init_drawer } from "./drawer.js";

export function initComponents() {
  init_trust_gauge();
  init_scan_reveal();
  init_privacy_lens();
  init_command_palette();
  init_drawer();
}
```

- [ ] **Step 3: Reference the entry in `index.html`**

In `app/templates/index.html`, just before `</body>` (find the existing closing `</body>` tag), insert:

```html
<script type="module">
  import { initComponents } from "/static/js/components/index.js?v={{ASSET_VERSION}}";
  document.addEventListener("DOMContentLoaded", initComponents);
</script>
```

- [ ] **Step 4: Verify page loads without console errors**

Open `http://localhost:8000/ui` in a browser. Open devtools console. Expected: no 404, no JS errors.

- [ ] **Step 5: Commit**

```bash
git add app/static/js/components/ app/templates/index.html
git commit -m "chore(redesign): scaffold signature component modules"
```

---

## Phase 1 · Tokens & primitives

### Task 1.1: Write integration test for new tokens

**Files:**
- Create: `tests/api/test_redesign_structure.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests asserting the redesign structural elements are present on /ui."""

from __future__ import annotations

import pytest


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
    # No legacy purple gradient brand token
    assert "--grad-brand" not in css
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/api/test_redesign_structure.py::test_ui_uses_new_design_tokens -v`
Expected: FAIL (because `tokens.css` is still empty).

### Task 1.2: Populate `tokens.css` with light + dark tokens

**Files:**
- Modify: `app/static/css/tokens.css`

- [ ] **Step 1: Write the tokens**

Replace the empty `tokens.css` with the full token set from spec §3.1 + §3.2:

```css
/* ConfiDoc — tokens.css */
/* Source of truth: docs/superpowers/specs/2026-05-23-confidoc-dashboard-redesign-design.md §3 */

:root {
  /* Surfaces */
  --surface: #FAFAF7;
  --surface-2: #FFFFFF;
  --surface-muted: #F0EFE9;
  --border: #ECEBE4;
  --border-strong: #D6D3C6;

  /* Ink (text) */
  --ink: #0F0F12;
  --ink-2: #3F3F44;
  --ink-muted: #6E6E72;
  --ink-dim: #9A9A9F;

  /* Narrative accents */
  --accent: #047857;
  --accent-soft: #ECFDF5;
  --accent-soft-ink: #065F46;
  --accent-border: #A7F3D0;
  --raw: #A4471E;
  --raw-soft: #FDF6F1;
  --raw-soft-ink: #A4471E;

  /* Status */
  --warning: #B45309;
  --warning-soft: #FEF3C7;
  --warning-soft-ink: #92400E;
  --danger: #B91C1C;
  --info: #5B21B6;
  --info-soft: #EDE9FE;

  /* Radii */
  --r-xs: 4px;
  --r-sm: 5px;
  --r-md: 7px;
  --r-lg: 8px;
  --r-xl: 10px;
  --r-2xl: 14px;

  /* Motion */
  --t-fast: 120ms ease-out;
  --t-drawer: 200ms cubic-bezier(0.16, 1, 0.3, 1);
  --t-gauge: 900ms cubic-bezier(0.16, 1, 0.3, 1);
  --t-scan: 600ms cubic-bezier(0.4, 0, 0.2, 1);

  /* Single allowed shadow */
  --shadow-docked: 0 24px 60px -28px rgba(0, 0, 0, 0.18);
}

[data-theme="dark"] {
  --surface: #0A0A14;
  --surface-2: #15151F;
  --surface-muted: #1F1F2A;
  --border: rgba(255, 255, 255, 0.06);
  --border-strong: rgba(255, 255, 255, 0.10);
  --ink: #EDEDF5;
  --ink-2: #C5C5D2;
  --ink-muted: #A0A0B8;
  --ink-dim: #7A7A92;
  --accent: #10B981;
  --accent-soft: rgba(16, 185, 129, 0.12);
  --accent-soft-ink: #6EE7B7;
  --accent-border: rgba(16, 185, 129, 0.35);
  --raw: #C97B5C;
  --raw-soft: rgba(201, 123, 92, 0.10);
  --raw-soft-ink: #E0A88A;
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --t-fast: 0ms;
    --t-drawer: 0ms;
    --t-gauge: 0ms;
    --t-scan: 0ms;
  }
}
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `pytest tests/api/test_redesign_structure.py::test_ui_uses_new_design_tokens -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add app/static/css/tokens.css tests/api/test_redesign_structure.py
git commit -m "feat(redesign): add narrative-color design tokens"
```

### Task 1.3: Populate `base.css` (reset, typography, fonts)

**Files:**
- Modify: `app/static/css/base.css`
- Modify: `app/templates/index.html` (font preconnect for JetBrains Mono + Iowan fallback)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_redesign_structure.py`:

```python
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
```

Run: `pytest tests/api/test_redesign_structure.py -v -k "base_loads or preconnects"`
Expected: FAIL (both tests fail).

- [ ] **Step 2: Write `base.css`**

```css
/* ConfiDoc — base.css */

*, *::before, *::after { box-sizing: border-box; }

html, body {
  margin: 0;
  padding: 0;
  background: var(--surface);
  color: var(--ink);
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.literary {
  font-family: 'Iowan Old Style', 'Palatino Linotype', 'Times New Roman', Georgia, serif;
  font-style: italic;
  font-weight: 500;
  color: var(--accent);
}

.mono {
  font-family: 'JetBrains Mono', ui-monospace, Menlo, monospace;
}

.tabular { font-variant-numeric: tabular-nums; }

h1, h2, h3, h4 {
  letter-spacing: -0.02em;
  line-height: 1.3;
  margin: 0;
}

.skip-link {
  position: absolute; left: -9999px; top: 0;
  background: var(--ink); color: var(--surface-2);
  padding: 8px 14px; border-radius: var(--r-md);
}
.skip-link:focus { left: 12px; top: 12px; z-index: 9999; }

:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: var(--r-xs);
}

@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0ms !important; transition-duration: 0ms !important; }
}
```

- [ ] **Step 3: Update `<head>` of `app/templates/index.html` to preload JetBrains Mono**

Find the existing Google Fonts link (around line 9) and replace with:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
```

(Iowan Old Style is OS-provided; no remote font for it — we rely on the fallback chain `Iowan Old Style → Palatino Linotype → Times New Roman → Georgia`.)

- [ ] **Step 4: Run the tests**

Run: `pytest tests/api/test_redesign_structure.py -v -k "base_loads or preconnects"`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add app/static/css/base.css app/templates/index.html tests/api/test_redesign_structure.py
git commit -m "feat(redesign): base typography, signature fonts, reduced motion"
```

### Task 1.4: Build `components.css` — Button, Pill, Chip, Segment

**Files:**
- Modify: `app/static/css/components.css`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_redesign_structure.py`:

```python
@pytest.mark.anyio
async def test_components_css_defines_primitives(client):
    resp = await client.get("/static/css/components.css")
    assert resp.status_code == 200
    css = resp.text
    for selector in [".btn-primary", ".btn-ghost", ".pill", ".chip", ".segment"]:
        assert selector in css, f"missing {selector}"
```

Run: `pytest tests/api/test_redesign_structure.py::test_components_css_defines_primitives -v`
Expected: FAIL.

- [ ] **Step 2: Write the component primitives**

Replace `app/static/css/components.css` with:

```css
/* ConfiDoc — components.css */

/* Buttons */
.btn-primary, .btn-primary-ok, .btn-ghost {
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  padding: 7px 14px;
  border-radius: var(--r-md);
  border: 1px solid;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background var(--t-fast), border-color var(--t-fast), color var(--t-fast);
}
.btn-primary { background: var(--ink); color: var(--surface-2); border-color: var(--ink); }
.btn-primary:hover { background: var(--ink-2); }
.btn-primary-ok { background: var(--accent); color: #fff; border-color: var(--accent); }
.btn-primary-ok:hover { background: var(--accent-soft-ink); }
.btn-ghost { background: var(--surface-2); color: var(--ink-2); border-color: var(--border); font-weight: 500; }
.btn-ghost:hover { background: var(--surface-muted); border-color: var(--border-strong); }

/* Pills (state badges) */
.pill {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--surface-muted);
  color: var(--ink-2);
}
.pill-anon { background: var(--accent-soft); color: var(--accent-soft-ink); }
.pill-review { background: var(--warning-soft); color: var(--warning-soft-ink); }
.pill-draft { background: var(--surface-muted); color: var(--ink-2); }
.pill-exported { background: var(--info-soft); color: var(--info); }
.pill-danger { background: #fee2e2; color: #991b1b; }

/* Chips (filter widgets) */
.chip {
  padding: 5px 10px;
  border-radius: var(--r-md);
  font-size: 11px;
  font-weight: 500;
  color: var(--ink-2);
  background: var(--surface-2);
  border: 1px solid var(--border);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  transition: border-color var(--t-fast);
}
.chip:hover { border-color: var(--border-strong); }
.chip.is-active { border-color: var(--ink); }

/* Segment control */
.segment {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
}
.segment > [data-segment] {
  padding: 5px 12px;
  border-radius: var(--r-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--ink-muted);
  cursor: pointer;
  background: transparent;
  border: 0;
  font-family: inherit;
  transition: background var(--t-fast), color var(--t-fast);
}
.segment > [data-segment][aria-pressed="true"] {
  background: var(--surface-2);
  color: var(--ink);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.segment > [data-segment] .count {
  font-size: 11px;
  color: var(--ink-dim);
  margin-left: 5px;
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 3: Run the test**

Run: `pytest tests/api/test_redesign_structure.py::test_components_css_defines_primitives -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/static/css/components.css tests/api/test_redesign_structure.py
git commit -m "feat(redesign): button, pill, chip, segment primitives"
```

### Task 1.5: Extend `components.css` — Card, KPICard, Input, Table, NavItem

**Files:**
- Modify: `app/static/css/components.css`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_redesign_structure.py`:

```python
@pytest.mark.anyio
async def test_components_css_defines_layout_pieces(client):
    resp = await client.get("/static/css/components.css")
    css = resp.text
    for selector in [".card", ".kpi-card", ".input", ".table", ".nav-item"]:
        assert selector in css, f"missing {selector}"
```

Run: `pytest tests/api/test_redesign_structure.py::test_components_css_defines_layout_pieces -v`
Expected: FAIL.

- [ ] **Step 2: Add the layout primitives to `components.css`**

Append to `app/static/css/components.css`:

```css
/* Cards */
.card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: 16px;
}

.kpi-card { padding: 14px 16px; }
.kpi-card .kpi-label {
  font-size: 11px;
  color: var(--ink-muted);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}
.kpi-card .kpi-value {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.kpi-card .kpi-delta {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  margin-top: 2px;
}
.kpi-card .kpi-delta.is-warning { color: var(--warning); }
.kpi-card.kpi-card--trust .kpi-value { color: var(--accent); }

/* Inputs */
.input {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 6px 10px;
  font-size: 13px;
  font-family: inherit;
  color: var(--ink);
  transition: border-color var(--t-fast);
}
.input:focus {
  border-color: var(--accent);
  outline: 3px solid var(--accent-soft);
  outline-offset: -1px;
}

/* Tables */
.table { width: 100%; border-collapse: collapse; }
.table thead th {
  text-align: left;
  font-size: 10px;
  font-weight: 700;
  color: var(--ink-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  background: var(--surface);
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
}
.table tbody td {
  padding: 11px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  vertical-align: middle;
}
.table tbody tr:hover { background: var(--surface); }

/* Nav items */
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border-radius: var(--r-md);
  font-size: 13px;
  color: var(--ink-2);
  cursor: pointer;
  text-decoration: none;
  border: 0;
  background: transparent;
  font-family: inherit;
  width: 100%;
  text-align: left;
  transition: background var(--t-fast), color var(--t-fast);
}
.nav-item:hover { background: var(--surface-muted); }
.nav-item[aria-current="page"] {
  background: var(--ink);
  color: var(--surface-2);
  font-weight: 600;
}
.nav-item .badge {
  margin-left: auto;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}
```

- [ ] **Step 3: Run the test**

Run: `pytest tests/api/test_redesign_structure.py::test_components_css_defines_layout_pieces -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/static/css/components.css tests/api/test_redesign_structure.py
git commit -m "feat(redesign): card, kpi-card, input, table, nav-item primitives"
```

---

## Phase 2 · Signature components

### Task 2.1: Token-card CSS

**Files:**
- Modify: `app/static/css/signatures.css`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_redesign_structure.py`:

```python
@pytest.mark.anyio
async def test_signatures_define_token_card(client):
    resp = await client.get("/static/css/signatures.css")
    assert resp.status_code == 200
    css = resp.text
    assert ".token-card" in css
    assert "JetBrains Mono" in css
    assert "linear-gradient" in css  # the subtle inner gradient on token-card
```

Run: `pytest tests/api/test_redesign_structure.py::test_signatures_define_token_card -v`
Expected: FAIL.

- [ ] **Step 2: Add `.token-card` to `signatures.css`**

```css
/* ConfiDoc — signatures.css */
/* §3.5 — The Signature Layer */

/* §3.5.1 — Token card */
.token-card {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--r-xs);
  border: 1px solid var(--accent-border);
  background: linear-gradient(180deg, var(--surface-2) 0%, var(--accent-soft) 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8),
              0 1px 0 rgba(4, 120, 87, 0.06);
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  cursor: pointer;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.token-card:hover {
  border-color: var(--accent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8),
              0 0 0 3px var(--accent-soft);
}
.token-card[aria-pressed="true"] {
  border-color: var(--accent);
  background: var(--accent-soft);
}

/* Raw highlight on the Original pane */
.pii-raw {
  background: rgba(164, 71, 30, 0.13);
  color: var(--raw);
  padding: 1px 3px;
  border-radius: 3px;
  font-weight: 500;
}
```

- [ ] **Step 3: Run the test**

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/static/css/signatures.css tests/api/test_redesign_structure.py
git commit -m "feat(signature): token-card and PII raw highlight"
```

### Task 2.2: Trust Gauge — JS web component (failing test first)

**Files:**
- Create: `tests/static/test_trust_gauge.html`
- Modify: `app/static/js/components/trust-gauge.js`
- Modify: `app/static/css/signatures.css`

- [ ] **Step 1: Write the JS test page (failing test)**

Create `tests/static/test_trust_gauge.html`:

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Trust Gauge unit test</title></head>
<body>
<div id="results"></div>
<script type="module">
import "/static/js/components/trust-gauge.js";

const results = document.getElementById("results");
const assert = (cond, name) => {
  const li = document.createElement("li");
  li.textContent = (cond ? "PASS · " : "FAIL · ") + name;
  li.style.color = cond ? "green" : "red";
  results.appendChild(li);
};

// 1. Element registered
assert(customElements.get("trust-gauge") !== undefined, "trust-gauge custom element is defined");

// 2. Renders 4 rings from attributes
const el = document.createElement("trust-gauge");
el.setAttribute("data-pii", "100");
el.setAttribute("data-quasi", "72");
el.setAttribute("data-coherence", "96");
el.setAttribute("data-reversibility", "100");
document.body.appendChild(el);
await new Promise(r => setTimeout(r, 50));
const circles = el.shadowRoot ? el.shadowRoot.querySelectorAll("circle") : el.querySelectorAll("circle");
assert(circles.length >= 8, "renders 8 circles (4 backgrounds + 4 progress)");

// 3. Computes global score as min of four (most restrictive)
const center = (el.shadowRoot || el).querySelector("[data-role=value]");
assert(center && center.textContent.trim().startsWith("72"), "global value uses min of dimensions");

window.__testsDone = true;
</script>
<ul id="results"></ul>
</body></html>
```

Open the page in a browser: `http://localhost:8000/static/../tests/static/test_trust_gauge.html` — or set up a static route. Easiest: temporarily mount `/tests-static/`:

For now, run via headless: `npx playwright-cli or` simply open in browser and check console. (If Playwright not installed, manual visual check is acceptable for this task — the JS tests are diagnostic, not gating.)

Expected: FAIL ("trust-gauge custom element is defined" fails because component is empty).

- [ ] **Step 2: Implement the Trust Gauge component**

Replace `app/static/js/components/trust-gauge.js`:

```js
// ConfiDoc — Trust Gauge component (§3.5.2)

const RINGS = [
  { attr: "pii",           r: 17, label: "PII directs" },
  { attr: "coherence",     r: 26, label: "Cohérence tokens" },
  { attr: "reversibility", r: 35, label: "Réversibilité" },
  { attr: "quasi",         r: 44, label: "Quasi-identifiants" },
];

class TrustGauge extends HTMLElement {
  static get observedAttributes() {
    return RINGS.map(r => `data-${r.attr}`);
  }
  connectedCallback() { this.render(); }
  attributeChangedCallback() { if (this.isConnected) this.render(); }

  render() {
    const size = parseInt(this.getAttribute("data-size") || "140", 10);
    const showCenter = this.getAttribute("data-mini") !== "true";
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const values = RINGS.map(r => Math.max(0, Math.min(100, parseInt(this.getAttribute(`data-${r.attr}`) || "0", 10))));
    const globalScore = Math.min(...values);

    const colorFor = v => v >= 90 ? "var(--accent)" : v >= 70 ? "var(--warning)" : "var(--danger)";

    const rings = RINGS.map((ring, i) => {
      const circumference = 2 * Math.PI * ring.r;
      const value = values[i];
      const offset = circumference * (1 - value / 100);
      return `
        <circle cx="50" cy="50" r="${ring.r}" fill="none" stroke="var(--border)" stroke-width="4"/>
        <circle data-ring="${ring.attr}" cx="50" cy="50" r="${ring.r}" fill="none"
                stroke="${colorFor(value)}" stroke-width="4" stroke-linecap="round"
                stroke-dasharray="${circumference}"
                stroke-dashoffset="${reduced ? offset : circumference}"
                style="transition: stroke-dashoffset var(--t-gauge);"/>
      `;
    }).join("");

    this.innerHTML = `
      <div class="trust-gauge-wrap" style="position:relative;width:${size}px;height:${size}px">
        <svg viewBox="0 0 100 100" width="${size}" height="${size}" style="transform:rotate(-90deg)">
          ${rings}
        </svg>
        ${showCenter ? `
          <div class="trust-gauge-center" style="position:absolute;inset:0;display:grid;place-items:center;text-align:center">
            <div>
              <div data-role="value" class="tabular" style="font-size:${size*0.21}px;font-weight:800;letter-spacing:-0.025em;color:${colorFor(globalScore)};line-height:1">
                ${globalScore}<span style="font-size:${size*0.10}px;opacity:0.6">%</span>
              </div>
              <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:var(--ink-muted);font-weight:700;margin-top:4px">Trust</div>
            </div>
          </div>` : ""}
      </div>
    `;

    if (!reduced) {
      requestAnimationFrame(() => {
        this.querySelectorAll("[data-ring]").forEach((c, i) => {
          const circumference = 2 * Math.PI * RINGS[i].r;
          const offset = circumference * (1 - values[i] / 100);
          c.style.strokeDashoffset = offset;
        });
      });
    }
  }
}

customElements.define("trust-gauge", TrustGauge);

export function init_trust_gauge() { /* element auto-registers on import */ }
```

- [ ] **Step 3: Re-open the test page in browser and verify**

Open `http://localhost:8000/tests-static/test_trust_gauge.html` (add a temporary FastAPI static mount for `/tests-static/` pointing to `tests/static/`, or copy the test file under `app/static/__dev__/` for the duration).

Quick mount: add to `app/main.py` (you'll remove this at the end):

```python
# Dev-only: serve unit-test HTML pages
import os
if os.getenv("CONFIDOC_DEV_TESTS"):
    from fastapi.staticfiles import StaticFiles
    app.mount("/tests-static", StaticFiles(directory="tests/static"), name="tests-static")
```

Run: `CONFIDOC_DEV_TESTS=1 uvicorn app.main:app --port 8000 --reload &` then open the URL.

Expected: 3 green PASS lines.

- [ ] **Step 4: Commit**

```bash
git add app/static/js/components/trust-gauge.js tests/static/test_trust_gauge.html app/main.py
git commit -m "feat(signature): Trust Gauge 4-ring web component"
```

### Task 2.3: Hero Literary helper class + smoke render

**Files:**
- Modify: `app/static/css/signatures.css`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_redesign_structure.py`:

```python
@pytest.mark.anyio
async def test_signatures_define_hero_literary(client):
    resp = await client.get("/static/css/signatures.css")
    css = resp.text
    assert ".hero-literary" in css
    assert "font-style: italic" in css
```

Run: `pytest tests/api/test_redesign_structure.py::test_signatures_define_hero_literary -v`
Expected: FAIL.

- [ ] **Step 2: Append `.hero-literary` to `signatures.css`**

```css
/* §3.5.3 — Hero literary */
.hero-literary {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.35;
  color: var(--ink);
  max-width: 640px;
}
.hero-literary em.literary,
.hero-literary .literary {
  font-family: 'Iowan Old Style', 'Palatino Linotype', 'Times New Roman', Georgia, serif;
  font-style: italic;
  font-weight: 500;
  color: var(--accent);
}
.hero-literary + .hero-lead {
  font-size: 13px;
  color: var(--ink-muted);
  margin-top: 8px;
}
```

- [ ] **Step 3: Run the test**

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/static/css/signatures.css tests/api/test_redesign_structure.py
git commit -m "feat(signature): hero literary line styling"
```

### Task 2.4: Scan Reveal — JS overlay helper

**Files:**
- Create: `tests/static/test_scan_reveal.html`
- Modify: `app/static/js/components/scan-reveal.js`
- Modify: `app/static/css/signatures.css`

- [ ] **Step 1: Add CSS for scan reveal**

Append to `app/static/css/signatures.css`:

```css
/* §3.5.4 — Scan reveal */
.scan-reveal {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 50;
}
.scan-reveal__line {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--accent) 30%, var(--accent) 70%, transparent);
  box-shadow: 0 0 12px rgba(4, 120, 87, 0.5);
  transform: translateY(0);
}
.scan-reveal__halo {
  position: absolute;
  left: 0;
  right: 0;
  top: 1px;
  height: 60px;
  background: linear-gradient(180deg, rgba(4, 120, 87, 0.08), transparent);
}
.scan-reveal--running .scan-reveal__line,
.scan-reveal--running .scan-reveal__halo {
  animation: scan-sweep var(--t-scan) cubic-bezier(0.4, 0, 0.2, 1) forwards;
}
@keyframes scan-sweep {
  from { transform: translateY(0); }
  to   { transform: translateY(calc(100% - 2px)); }
}

.scan-reveal__check {
  position: absolute;
  left: 50%; top: 50%;
  width: 36px; height: 36px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 18px;
  transform: translate(-50%, -50%) scale(0);
  opacity: 0;
}
.scan-reveal--done .scan-reveal__check {
  animation: scan-check 200ms cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
@keyframes scan-check {
  from { transform: translate(-50%, -50%) scale(0.6); opacity: 0; }
  to   { transform: translate(-50%, -50%) scale(1); opacity: 1; }
}
```

- [ ] **Step 2: Implement the JS helper**

Replace `app/static/js/components/scan-reveal.js`:

```js
// ConfiDoc — Scan Reveal (§3.5.4)
// Public API:
//   triggerScanReveal(rootEl, { onDone }) — single ceremonial animation
//   Returns a Promise that resolves after the animation ends.

export function triggerScanReveal(rootEl, { onDone } = {}) {
  if (!rootEl) return Promise.resolve();
  rootEl.style.position = rootEl.style.position || "relative";

  const overlay = document.createElement("div");
  overlay.className = "scan-reveal scan-reveal--running";
  overlay.setAttribute("role", "status");
  overlay.setAttribute("aria-live", "polite");
  overlay.innerHTML = `
    <div class="scan-reveal__halo"></div>
    <div class="scan-reveal__line"></div>
    <div class="scan-reveal__check" aria-hidden="true">✓</div>
  `;
  rootEl.appendChild(overlay);

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const lineDuration = reduced ? 0 : 600;

  return new Promise(resolve => {
    setTimeout(() => {
      overlay.classList.remove("scan-reveal--running");
      overlay.classList.add("scan-reveal--done");
      setTimeout(() => {
        onDone?.();
        // Keep the check visible briefly, then clean up
        setTimeout(() => overlay.remove(), 1200);
        resolve();
      }, reduced ? 0 : 220);
    }, lineDuration);
  });
}

// Export the auto-init no-op (matches other components)
export function init_scan_reveal() { window.triggerScanReveal = triggerScanReveal; }
```

- [ ] **Step 3: Add JS unit test page**

Create `tests/static/test_scan_reveal.html`:

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>Scan Reveal unit test</title>
<link rel="stylesheet" href="/static/css/style.css">
</head>
<body style="padding:24px">
<div id="target" style="width:400px;height:300px;background:#fafaf7;border:1px solid #ecebe4;border-radius:14px"></div>
<button id="trigger" style="margin-top:12px">Trigger scan reveal</button>
<pre id="result"></pre>
<script type="module">
import { triggerScanReveal, init_scan_reveal } from "/static/js/components/scan-reveal.js";
init_scan_reveal();

document.getElementById("trigger").addEventListener("click", async () => {
  const t0 = performance.now();
  await triggerScanReveal(document.getElementById("target"));
  const dt = Math.round(performance.now() - t0);
  document.getElementById("result").textContent = "Scan reveal completed in " + dt + "ms";
});
</script>
</body></html>
```

- [ ] **Step 4: Manual verification**

Open `http://localhost:8000/tests-static/test_scan_reveal.html`, click "Trigger scan reveal". Expected: emerald line sweeps top-to-bottom in ~600ms, then a checkmark appears with a slight bounce, then it fades.

- [ ] **Step 5: Commit**

```bash
git add app/static/css/signatures.css app/static/js/components/scan-reveal.js tests/static/test_scan_reveal.html
git commit -m "feat(signature): scan reveal ceremony"
```

### Task 2.5: Privacy Lens — toggle + heatmap overlay

**Files:**
- Modify: `app/static/css/signatures.css`
- Modify: `app/static/js/components/privacy-lens.js`

- [ ] **Step 1: Add CSS**

Append to `app/static/css/signatures.css`:

```css
/* §3.5.5 — Privacy Lens */
.privacy-lens-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  display: none;
  z-index: 5;
}
[data-privacy-lens="on"] .privacy-lens-overlay { display: block; }

.privacy-lens-zone {
  position: absolute;
  background: rgba(164, 71, 30, 0.18);
  border: 1px dashed rgba(164, 71, 30, 0.5);
  border-radius: 4px;
  font-size: 10px;
  color: var(--raw);
  padding: 2px 6px;
}
```

- [ ] **Step 2: Implement the JS**

Replace `app/static/js/components/privacy-lens.js`:

```js
// ConfiDoc — Privacy Lens (§3.5.5)
// Reads <div data-privacy-zones="..."> with a JSON array of {top,left,width,height,risk,label}
// Toggles overlay visibility via the data-privacy-lens attribute on the closest [data-document-detail].

export function init_privacy_lens() {
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "l") {
      const root = document.querySelector("[data-document-detail]");
      if (!root) return;
      e.preventDefault();
      togglePrivacyLens(root);
    }
  });

  document.querySelectorAll("[data-privacy-lens-toggle]").forEach(btn => {
    btn.addEventListener("click", () => {
      const root = btn.closest("[data-document-detail]") || document.querySelector("[data-document-detail]");
      if (root) togglePrivacyLens(root);
    });
  });
}

function togglePrivacyLens(root) {
  const on = root.getAttribute("data-privacy-lens") === "on";
  root.setAttribute("data-privacy-lens", on ? "off" : "on");
  renderZones(root);
}

function renderZones(root) {
  const container = root.querySelector(".privacy-lens-overlay");
  if (!container) return;
  if (root.getAttribute("data-privacy-lens") !== "on") { container.innerHTML = ""; return; }

  const rawZones = root.getAttribute("data-privacy-zones");
  if (!rawZones) return;
  let zones;
  try { zones = JSON.parse(rawZones); } catch { return; }
  container.innerHTML = zones.map(z =>
    `<div class="privacy-lens-zone" style="top:${z.top};left:${z.left};width:${z.width};height:${z.height}" title="${z.label || ""}">${z.label || ""}</div>`
  ).join("");
}
```

- [ ] **Step 3: Manual smoke test**

Add temporarily to `index.html` (will be wired properly later in Phase 5):

```html
<div data-document-detail data-privacy-zones='[{"top":"20px","left":"24px","width":"180px","height":"22px","label":"Adresse partielle"}]'>
  <div class="privacy-lens-overlay"></div>
  <button data-privacy-lens-toggle>Toggle Privacy Lens</button>
  <p style="padding:24px">Lorem ipsum 12 rue Lafayette Paris.</p>
</div>
```

Reload, click the toggle (or press ⌘L). Expected: terracotta zone appears over the address text.

Revert the temporary block (don't commit it).

- [ ] **Step 4: Commit**

```bash
git add app/static/css/signatures.css app/static/js/components/privacy-lens.js
git commit -m "feat(signature): privacy lens toggle and overlay"
```

### Task 2.6: Command palette ⌘K — skeleton

**Files:**
- Modify: `app/static/js/components/command-palette.js`
- Modify: `app/static/css/signatures.css`

- [ ] **Step 1: Add CSS for the palette dialog**

Append to `app/static/css/signatures.css`:

```css
/* Command palette ⌘K */
.cmd-palette {
  position: fixed;
  inset: 0;
  background: rgba(15, 15, 18, 0.4);
  display: none;
  align-items: flex-start;
  justify-content: center;
  padding-top: 12vh;
  z-index: 9000;
}
.cmd-palette[open] { display: flex; }
.cmd-palette__panel {
  width: 100%;
  max-width: 560px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--r-2xl);
  box-shadow: var(--shadow-docked);
  overflow: hidden;
}
.cmd-palette__input {
  width: 100%;
  border: 0;
  font-family: inherit;
  font-size: 15px;
  padding: 16px 20px;
  background: transparent;
  color: var(--ink);
  outline: 0;
  border-bottom: 1px solid var(--border);
}
.cmd-palette__list {
  max-height: 320px;
  overflow: auto;
  padding: 6px 0;
}
.cmd-palette__item {
  padding: 9px 20px;
  font-size: 13px;
  color: var(--ink-2);
  cursor: pointer;
  display: flex;
  justify-content: space-between;
}
.cmd-palette__item[aria-selected="true"] {
  background: var(--surface);
  color: var(--ink);
}
.cmd-palette__hint { color: var(--ink-dim); font-size: 11px; }
```

- [ ] **Step 2: Implement the palette JS**

Replace `app/static/js/components/command-palette.js`:

```js
// ConfiDoc — Command palette ⌘K
const ACTIONS = [
  { label: "Aller à Accueil",         hint: "Nav · Accueil",    do: () => navTo("home") },
  { label: "Aller à Documents",       hint: "Nav · Documents",  do: () => navTo("documents") },
  { label: "Aller à Dossiers",        hint: "Nav · Dossiers",   do: () => navTo("clients") },
  { label: "Aller à Qualité & RGPD",  hint: "Nav · Qualité",    do: () => navTo("quality") },
  { label: "Aller à Journal d'audit", hint: "Nav · Audit",      do: () => navTo("audit") },
  { label: "Aller à Paramètres",      hint: "Nav · Paramètres", do: () => navTo("settings") },
  { label: "Importer un document",    hint: "Action · Upload",  do: () => document.querySelector('[data-action="open-upload"]')?.click() },
];

function navTo(key) {
  const btn = document.querySelector(`[data-nav="${key}"]`);
  if (btn) btn.click();
}

export function init_command_palette() {
  const palette = ensureDom();
  const input = palette.querySelector(".cmd-palette__input");
  const list = palette.querySelector(".cmd-palette__list");
  let filtered = ACTIONS;
  let selected = 0;

  const render = () => {
    list.innerHTML = filtered.map((a, i) =>
      `<div class="cmd-palette__item" role="option" aria-selected="${i === selected}" data-i="${i}">
         <span>${a.label}</span><span class="cmd-palette__hint">${a.hint}</span>
       </div>`
    ).join("");
  };
  const close = () => { palette.removeAttribute("open"); input.value = ""; };
  const open = () => {
    filtered = ACTIONS; selected = 0; render();
    palette.setAttribute("open", "");
    setTimeout(() => input.focus(), 0);
  };
  const run = i => { filtered[i]?.do(); close(); };

  input.addEventListener("input", () => {
    const q = input.value.toLowerCase().trim();
    filtered = q ? ACTIONS.filter(a => a.label.toLowerCase().includes(q)) : ACTIONS;
    selected = 0; render();
  });
  list.addEventListener("click", e => {
    const t = e.target.closest("[data-i]"); if (t) run(+t.dataset.i);
  });
  palette.addEventListener("click", e => { if (e.target === palette) close(); });

  document.addEventListener("keydown", e => {
    const open_p = palette.hasAttribute("open");
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); open_p ? close() : open(); return; }
    if (!open_p) return;
    if (e.key === "Escape") { e.preventDefault(); close(); }
    if (e.key === "ArrowDown") { e.preventDefault(); selected = (selected + 1) % filtered.length; render(); }
    if (e.key === "ArrowUp")   { e.preventDefault(); selected = (selected - 1 + filtered.length) % filtered.length; render(); }
    if (e.key === "Enter")     { e.preventDefault(); run(selected); }
  });
}

function ensureDom() {
  let palette = document.getElementById("cmd-palette");
  if (palette) return palette;
  palette = document.createElement("div");
  palette.id = "cmd-palette";
  palette.className = "cmd-palette";
  palette.setAttribute("role", "dialog");
  palette.setAttribute("aria-modal", "true");
  palette.innerHTML = `
    <div class="cmd-palette__panel">
      <input class="cmd-palette__input" placeholder="Chercher un document, un client, une action…" aria-label="Recherche globale" />
      <div class="cmd-palette__list" role="listbox"></div>
    </div>
  `;
  document.body.appendChild(palette);
  return palette;
}
```

- [ ] **Step 3: Manual verification**

Reload `/ui`. Press ⌘K. Expected: palette opens, type "doc" filters to Documents/Upload, arrow keys move selection, Enter triggers navigation, Esc closes.

- [ ] **Step 4: Commit**

```bash
git add app/static/css/signatures.css app/static/js/components/command-palette.js
git commit -m "feat(signature): command palette ⌘K"
```

### Task 2.7: Drawer ⌘J — Copilot shell

**Files:**
- Modify: `app/static/js/components/drawer.js`
- Modify: `app/static/css/signatures.css`

- [ ] **Step 1: Add CSS**

Append to `app/static/css/signatures.css`:

```css
/* Drawer (Copilot ⌘J) */
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 15, 18, 0.4);
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--t-drawer);
  z-index: 8000;
}
.drawer-backdrop[open] { opacity: 1; pointer-events: auto; }
.drawer {
  position: fixed;
  top: 0; right: 0; bottom: 0;
  width: 420px;
  max-width: 90vw;
  background: var(--surface-2);
  border-left: 1px solid var(--border);
  box-shadow: var(--shadow-docked);
  transform: translateX(100%);
  transition: transform var(--t-drawer);
  z-index: 8001;
  display: flex;
  flex-direction: column;
}
.drawer[open] { transform: translateX(0); }
.drawer__header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.drawer__title { font-size: 13px; font-weight: 700; }
.drawer__close { background: transparent; border: 0; cursor: pointer; color: var(--ink-muted); font-size: 18px; }
.drawer__body { flex: 1; overflow: auto; padding: 16px 18px; }
```

- [ ] **Step 2: Implement the drawer JS**

Replace `app/static/js/components/drawer.js`:

```js
// ConfiDoc — Drawer (Copilot ⌘J)

export function init_drawer() {
  const { backdrop, drawer, body } = ensureDom();

  const open = () => {
    backdrop.setAttribute("open", "");
    drawer.setAttribute("open", "");
    populate(body);
  };
  const close = () => {
    backdrop.removeAttribute("open");
    drawer.removeAttribute("open");
  };

  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
      e.preventDefault();
      drawer.hasAttribute("open") ? close() : open();
    }
    if (e.key === "Escape" && drawer.hasAttribute("open")) close();
  });
  backdrop.addEventListener("click", close);
  drawer.querySelector(".drawer__close").addEventListener("click", close);
}

function populate(body) {
  const docName = document.querySelector("[data-active-document]")?.textContent?.trim();
  body.innerHTML = `
    <p style="margin:0 0 12px;font-size:13px;color:var(--ink-2)">
      ${docName ? `Tu travailles sur <strong>${docName}</strong>.` : "Aucun document ouvert."}
    </p>
    <textarea class="input" rows="6" style="width:100%" placeholder="Demande au Copilot…"></textarea>
    <p style="margin-top:10px;font-size:11px;color:var(--ink-dim)">⌘J pour fermer · le contenu détaillé arrive à l'étape Copilot.</p>
  `;
}

function ensureDom() {
  let drawer = document.getElementById("drawer-copilot");
  if (drawer) return { backdrop: document.getElementById("drawer-backdrop"), drawer, body: drawer.querySelector(".drawer__body") };
  const backdrop = document.createElement("div");
  backdrop.id = "drawer-backdrop";
  backdrop.className = "drawer-backdrop";
  document.body.appendChild(backdrop);
  drawer = document.createElement("aside");
  drawer.id = "drawer-copilot";
  drawer.className = "drawer";
  drawer.setAttribute("role", "complementary");
  drawer.setAttribute("aria-label", "Copilot IA");
  drawer.innerHTML = `
    <div class="drawer__header">
      <div class="drawer__title">Copilot IA</div>
      <button class="drawer__close" aria-label="Fermer">×</button>
    </div>
    <div class="drawer__body"></div>
  `;
  document.body.appendChild(drawer);
  return { backdrop, drawer, body: drawer.querySelector(".drawer__body") };
}
```

- [ ] **Step 3: Manual verification**

Reload `/ui`. Press ⌘J. Expected: drawer slides in from the right in ~200ms with backdrop. Press Esc or ⌘J → closes.

- [ ] **Step 4: Commit**

```bash
git add app/static/css/signatures.css app/static/js/components/drawer.js
git commit -m "feat(signature): copilot drawer ⌘J"
```

---

## Phase 3 · Topbar + Sidebar refactor

### Task 3.1: Test for new nav structure

**Files:**
- Modify: `tests/api/test_redesign_structure.py`

- [ ] **Step 1: Write failing assertions about the redesigned nav**

Append to `tests/api/test_redesign_structure.py`:

```python
@pytest.mark.anyio
async def test_sidebar_groups_nav_into_three_zones(client):
    resp = await client.get("/ui")
    html = resp.text
    # The nav now has 3 explicit group labels
    for label in ["Workspace", "Confiance", "Système"]:
        assert label in html, f"missing group label {label!r}"
    # The 6 destinations
    for nav in ["home", "documents", "clients", "quality", "audit", "settings"]:
        assert f'data-nav="{nav}"' in html, f"missing nav destination {nav}"
    # Old separated 'compliance' nav must be gone
    assert 'data-nav="compliance"' not in html


@pytest.mark.anyio
async def test_topbar_has_search_and_copilot_hints(client):
    resp = await client.get("/ui")
    html = resp.text
    assert "⌘K" in html
    assert "⌘J" in html
```

Run: `pytest tests/api/test_redesign_structure.py -v -k "sidebar_groups or topbar_has_search"`
Expected: both FAIL.

### Task 3.2: Restructure the sidebar markup

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Locate the existing sidebar block**

```bash
grep -n 'data-nav=' app/templates/index.html
```

Expected output: lines around 255–321 with 6 nav buttons.

- [ ] **Step 2: Replace the sidebar nav with the grouped version**

Replace the entire block of 6 nav-item buttons (between the opening `<nav>` and its closing `</nav>` tag for the sidebar) with:

```html
<nav class="app-nav" aria-label="Navigation principale">
  <div class="nav-group">
    <div class="nav-group__label">Workspace</div>
    <button class="nav-item" data-nav="home" type="button" aria-current="page">
      <span class="nav-item-icon" aria-hidden="true"></span>
      <span class="nav-item-label">Accueil</span>
    </button>
    <button class="nav-item" data-nav="documents" type="button">
      <span class="nav-item-icon" aria-hidden="true"></span>
      <span class="nav-item-label">Documents</span>
      <span class="badge" id="nav-documents-badge" hidden></span>
    </button>
    <button class="nav-item" data-nav="clients" type="button">
      <span class="nav-item-icon" aria-hidden="true"></span>
      <span class="nav-item-label">Dossiers</span>
    </button>
  </div>
  <div class="nav-group">
    <div class="nav-group__label">Confiance</div>
    <button class="nav-item" data-nav="quality" type="button">
      <span class="nav-item-icon" aria-hidden="true"></span>
      <span class="nav-item-label">Qualité &amp; RGPD</span>
    </button>
    <button class="nav-item" data-nav="audit" type="button">
      <span class="nav-item-icon" aria-hidden="true"></span>
      <span class="nav-item-label">Journal d'audit</span>
    </button>
  </div>
  <div class="nav-group">
    <div class="nav-group__label">Système</div>
    <button class="nav-item" data-nav="settings" type="button">
      <span class="nav-item-icon" aria-hidden="true"></span>
      <span class="nav-item-label">Paramètres</span>
    </button>
  </div>
</nav>
```

- [ ] **Step 3: Style `.nav-group` and `.nav-group__label` in `screens.css`**

Append to `app/static/css/screens.css`:

```css
/* App layout */
.app-nav {
  display: flex;
  flex-direction: column;
  padding: 12px 8px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  width: 220px;
  flex-shrink: 0;
}
.nav-group { margin-bottom: 18px; }
.nav-group__label {
  font-size: 10px;
  font-weight: 700;
  color: var(--ink-dim);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  padding: 0 10px 6px;
}
```

- [ ] **Step 4: Update `app.js` router to handle `audit` nav destination**

Find the existing nav-handler switch (search `data-nav` in `app.js`). Add a case for `audit` that shows `panel-audit` (we'll create this panel later — for now, route it to a placeholder).

In `app/static/js/app.js`, locate the nav routing function (search for `panel-quality` or `data-nav`). Insert a new case alongside the others:

```js
case "audit":
  setActivePanel("panel-audit");
  break;
```

If the function uses object lookup instead of switch, add the key the same way.

- [ ] **Step 5: Add empty placeholder panel for audit**

In `app/templates/index.html`, just before the closing `</main>`, add:

```html
<div id="panel-audit" class="panel">
  <div class="panel-stub">
    <p class="panel-stub-text">Journal d'audit — bientôt rempli (Phase 7).</p>
  </div>
</div>
```

- [ ] **Step 6: Run the nav tests**

Run: `pytest tests/api/test_redesign_structure.py -v -k "sidebar_groups"`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html app/static/css/screens.css app/static/js/app.js
git commit -m "feat(redesign): three-zone sidebar with audit destination"
```

### Task 3.3: Restructure the topbar

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/css/screens.css`

- [ ] **Step 1: Replace topbar content**

Locate `<header class="app-header glass">` in `index.html`. Replace its inner contents with:

```html
<div class="topbar">
  <div class="topbar__brand">
    <span class="brand-mark" aria-hidden="true">C</span>
    <span class="brand-text">ConfiDoc<span class="brand-dot">.</span></span>
  </div>
  <button type="button" class="topbar__search" data-action="open-cmd-palette">
    <span aria-hidden="true">⌕</span>
    <span>Chercher un document, un client, une action…</span>
    <span class="kbd" aria-hidden="true">⌘K</span>
  </button>
  <div class="topbar__actions">
    <span id="topbar-compliance" class="pill pill-anon" data-role="compliance">Conformité —</span>
    <button type="button" class="btn-ghost" data-action="open-copilot" aria-label="Ouvrir le Copilot IA">
      Copilot <span class="kbd">⌘J</span>
    </button>
    <button id="btn-theme" class="btn-ghost btn-theme-toggle" aria-label="Changer le thème" role="switch" aria-checked="false">Thème</button>
    <span id="user-info" class="user-info"></span>
    <button id="btn-logout" class="btn-ghost" style="display:none">Déconnexion</button>
  </div>
</div>
```

(Keep the old `id="btn-theme"` and `id="btn-logout"` so existing JS handlers keep working.)

- [ ] **Step 2: Style topbar**

Append to `app/static/css/screens.css`:

```css
.app-header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 10px 16px;
}
.topbar { display: flex; align-items: center; gap: 12px; }
.topbar__brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 14px;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.brand-mark {
  width: 22px;
  height: 22px;
  border-radius: var(--r-sm);
  background: var(--ink);
  color: var(--surface-2);
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 800;
}
.brand-dot { color: var(--accent); }
.topbar__search {
  flex: 1;
  max-width: 480px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 6px 10px;
  font-size: 12px;
  color: var(--ink-muted);
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  display: flex;
  align-items: center;
  gap: 8px;
}
.topbar__search:hover { border-color: var(--border-strong); }
.topbar__search .kbd { margin-left: auto; }
.topbar__actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }
.kbd {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  padding: 2px 5px;
  border: 1px solid var(--border);
  border-radius: var(--r-xs);
  background: var(--surface);
  color: var(--ink-muted);
}
```

- [ ] **Step 3: Wire the search button to ⌘K**

In `app/static/js/app.js`, after `initComponents()` call (or wherever event handlers are attached), add:

```js
document.querySelector('[data-action="open-cmd-palette"]')?.addEventListener("click", () => {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
});
document.querySelector('[data-action="open-copilot"]')?.addEventListener("click", () => {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "j", metaKey: true }));
});
```

- [ ] **Step 4: Run topbar test**

Run: `pytest tests/api/test_redesign_structure.py -v -k "topbar_has_search"`
Expected: PASS.

- [ ] **Step 5: Manual verification**

Reload `/ui`. Click the search bar → palette opens. Click "Copilot ⌘J" → drawer opens.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html app/static/css/screens.css app/static/js/app.js
git commit -m "feat(redesign): topbar with search, ⌘K, ⌘J entry points"
```

---

## Phase 4 · Documents (liste)

### Task 4.1: Failing test for new Documents layout

**Files:**
- Modify: `tests/api/test_redesign_structure.py`

- [ ] **Step 1: Append assertions**

```python
@pytest.mark.anyio
async def test_documents_panel_uses_segments_and_filters(client):
    resp = await client.get("/ui")
    html = resp.text
    # Segments
    for seg in ["seg-all", "seg-review", "seg-anon", "seg-draft", "seg-exported"]:
        assert f'data-segment="{seg}"' in html, f"missing segment {seg}"
    # Filter chips
    for chip in ["filter-dossier", "filter-type", "filter-trust", "filter-date"]:
        assert f'data-filter="{chip}"' in html, f"missing filter {chip}"
    # Mini trust gauge column header
    assert "data-col=\"trust\"" in html
```

Run: `pytest tests/api/test_redesign_structure.py -v -k "documents_panel_uses_segments"`
Expected: FAIL.

### Task 4.2: Refactor the Documents panel markup

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Locate the existing upload panel**

```bash
grep -n 'id="panel-upload"' app/templates/index.html
```

- [ ] **Step 2: Replace its content with the new Documents list**

Replace the entire `<div id="panel-upload" ...>...</div>` block with:

```html
<div id="panel-documents" class="panel">
  <header class="panel-head">
    <div>
      <h1 class="page-title">Documents</h1>
      <p class="page-lead" id="documents-summary">— · — · —</p>
    </div>
    <div class="panel-actions">
      <button class="btn-ghost" data-action="open-batch-upload">Importer un dossier</button>
      <button class="btn-primary" data-action="open-upload"><span aria-hidden="true">+</span> Nouveau document</button>
    </div>
  </header>

  <div class="segment" role="tablist" id="documents-segments">
    <button role="tab" data-segment="seg-all" aria-pressed="true">Tous <span class="count" data-count="all">—</span></button>
    <button role="tab" data-segment="seg-review" aria-pressed="false">À reviewer <span class="count" data-count="review">—</span></button>
    <button role="tab" data-segment="seg-anon" aria-pressed="false">Anonymisés <span class="count" data-count="anon">—</span></button>
    <button role="tab" data-segment="seg-draft" aria-pressed="false">Brouillons <span class="count" data-count="draft">—</span></button>
    <button role="tab" data-segment="seg-exported" aria-pressed="false">Exportés <span class="count" data-count="exported">—</span></button>
  </div>

  <div class="filter-bar">
    <input type="search" class="input" id="documents-search" placeholder="⌕ Filtrer par nom, dossier, client…">
    <button class="chip" data-filter="filter-dossier">Dossier · Tous ▾</button>
    <button class="chip" data-filter="filter-type">Type · Tous ▾</button>
    <button class="chip" data-filter="filter-trust">Trust ▾</button>
    <button class="chip" data-filter="filter-date">Date ▾</button>
  </div>

  <table class="table" id="documents-table">
    <thead>
      <tr>
        <th data-col="check" aria-label=""></th>
        <th data-col="name">Document</th>
        <th data-col="status">Statut</th>
        <th data-col="dossier">Dossier</th>
        <th data-col="trust">Trust</th>
        <th data-col="modified">Modifié</th>
        <th data-col="actions" aria-label=""></th>
      </tr>
    </thead>
    <tbody id="documents-tbody">
      <!-- rows rendered by app.js -->
    </tbody>
  </table>

  <div class="drop-zone" id="documents-dropzone" tabindex="0">
    <p><strong>Glisse un PDF ici</strong> pour démarrer une anonymisation, ou <button class="link" data-action="open-upload">parcours tes fichiers</button>.</p>
  </div>
</div>
```

- [ ] **Step 3: Style the new layout in `screens.css`**

Append:

```css
/* Panels common */
.panel { padding: 22px 26px; display: none; }
.panel.is-active { display: block; }
.panel-head { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 22px; gap: 16px; }
.page-title { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }
.page-lead { font-size: 13px; color: var(--ink-muted); margin-top: 4px; }
.panel-actions { display: flex; gap: 8px; }

/* Documents */
#documents-segments { margin-bottom: 14px; }
.filter-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
.filter-bar .input { flex: 1; min-width: 220px; max-width: 360px; }

.table th[data-col="trust"] { text-align: right; }
.table td[data-col="trust"] { text-align: right; }
.doc-name { display: flex; align-items: center; gap: 10px; min-width: 0; }
.doc-name__icon {
  width: 24px; height: 24px;
  background: var(--surface-muted);
  border-radius: var(--r-xs);
  display: grid; place-items: center;
  font-size: 10px; font-weight: 700; color: var(--ink-muted);
  flex-shrink: 0;
}
.doc-name__stack { line-height: 1.3; min-width: 0; }
.doc-name__main { font-weight: 500; }
.doc-name__meta { font-size: 11px; color: var(--ink-dim); }

.drop-zone {
  margin-top: 18px;
  padding: 22px;
  border: 1.5px dashed var(--border-strong);
  border-radius: var(--r-xl);
  text-align: center;
  background: var(--surface);
  color: var(--ink-muted);
  font-size: 12px;
}
.drop-zone strong { color: var(--ink); }
.drop-zone .link {
  background: transparent; border: 0; padding: 0; cursor: pointer;
  color: var(--accent); font-weight: 600; text-decoration: underline;
  font-family: inherit; font-size: inherit;
}
```

- [ ] **Step 4: Active panel toggle**

In `app/static/js/app.js`, ensure the nav router toggles `.is-active` on the matching panel (and removes it from others):

```js
export function setActivePanel(panelId) {
  document.querySelectorAll(".panel").forEach(p => p.classList.toggle("is-active", p.id === panelId));
  document.querySelectorAll("[data-nav]").forEach(b => b.setAttribute("aria-current", b.getAttribute(`data-panel`) === panelId ? "page" : "false"));
}
```

(If `setActivePanel` already exists with different semantics, integrate the new ID `panel-documents` into its mapping.)

- [ ] **Step 5: Map `data-nav="documents"` → `panel-documents`**

In the router map (search `data-nav` handlers in `app.js`), update so `documents` → `panel-documents`.

- [ ] **Step 6: Run the test**

Run: `pytest tests/api/test_redesign_structure.py -v -k "documents_panel_uses_segments"`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html app/static/css/screens.css app/static/js/app.js
git commit -m "feat(redesign): documents list with segments, filters, mini trust"
```

### Task 4.3: Render document rows with mini Trust Gauge

**Files:**
- Modify: `app/static/js/app.js`

- [ ] **Step 1: Locate the function that renders document rows**

```bash
grep -n "function.*[Rr]ender.*[Dd]oc\|panel-upload\|panel-anon\|document.*list" app/static/js/app.js | head -20
```

(The current code paints the legacy doc list. Find the matching renderer.)

- [ ] **Step 2: Add a new renderer `renderDocumentsTable(rows)`**

Add to `app/static/js/app.js`:

```js
function pillForStatus(status) {
  const m = { anon: "pill-anon", review: "pill-review", draft: "pill-draft", exported: "pill-exported", danger: "pill-danger" };
  const label = { anon: "Anonymisé", review: "À reviewer", draft: "Brouillon", exported: "Exporté", danger: "Erreur" }[status] || status;
  return `<span class="pill ${m[status] || ""}">${label}</span>`;
}

function trustMini(values) {
  // values: { pii, quasi, coherence, reversibility } 0-100
  return `<trust-gauge data-mini="true" data-size="40"
    data-pii="${values.pii ?? 0}"
    data-quasi="${values.quasi ?? 0}"
    data-coherence="${values.coherence ?? 0}"
    data-reversibility="${values.reversibility ?? 0}"></trust-gauge>`;
}

function renderDocumentsTable(rows) {
  const tbody = document.getElementById("documents-tbody");
  if (!tbody) return;
  tbody.innerHTML = rows.map(r => `
    <tr data-doc-id="${r.id}">
      <td data-col="check"><input type="checkbox" aria-label="Sélectionner ${r.name}"></td>
      <td data-col="name">
        <div class="doc-name">
          <div class="doc-name__icon">${(r.kind || "D")[0].toUpperCase()}</div>
          <div class="doc-name__stack">
            <div class="doc-name__main">${escapeHtml(r.name)}</div>
            <div class="doc-name__meta">${r.format || "PDF"} · ${r.pages || "—"} pages</div>
          </div>
        </div>
      </td>
      <td data-col="status">${pillForStatus(r.status)}</td>
      <td data-col="dossier">${escapeHtml(r.dossier || "—")}</td>
      <td data-col="trust">${trustMini(r.trust || {})}</td>
      <td data-col="modified" class="tabular">${r.modified || "—"}</td>
      <td data-col="actions">
        <button class="btn-ghost btn-xs" data-action="open-doc" data-doc-id="${r.id}">▶ Reviewer</button>
      </td>
    </tr>
  `).join("");
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));
}

window.renderDocumentsTable = renderDocumentsTable; // expose for the existing fetch pipeline
```

- [ ] **Step 3: Wire the existing fetch to call the new renderer**

Find where the existing code receives the documents list from the API (search for `/api/v1/documents` in `app.js`). After parsing the response, call `renderDocumentsTable(rows)` with a mapped payload (`id`, `name`, `kind`, `pages`, `status`, `dossier`, `trust: {pii, quasi, coherence, reversibility}`, `modified`).

If the API does not yet return trust dimensions, fall back to `{ pii: r.trust_score, quasi: r.trust_score, coherence: r.trust_score, reversibility: r.trust_score }`.

- [ ] **Step 4: Manual verification**

Reload `/ui`, navigate to Documents. Expected: table renders rows with mini Trust Gauges in the Trust column.

- [ ] **Step 5: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat(redesign): document rows with mini trust gauges"
```

### Task 4.4: Segment + chip behavior (filter the table client-side)

**Files:**
- Modify: `app/static/js/app.js`

- [ ] **Step 1: Add filter state and wire segments**

Append to `app.js`:

```js
const documentsState = { segment: "seg-all", query: "" };

document.addEventListener("click", e => {
  const segBtn = e.target.closest("#documents-segments [data-segment]");
  if (segBtn) {
    documentsState.segment = segBtn.dataset.segment;
    document.querySelectorAll("#documents-segments [data-segment]").forEach(b =>
      b.setAttribute("aria-pressed", b === segBtn ? "true" : "false"));
    applyDocumentsFilter();
  }
});
document.getElementById("documents-search")?.addEventListener("input", e => {
  documentsState.query = e.target.value.toLowerCase();
  applyDocumentsFilter();
});

function applyDocumentsFilter() {
  const tbody = document.getElementById("documents-tbody");
  if (!tbody) return;
  const statusForSeg = { "seg-all": null, "seg-review": "review", "seg-anon": "anon", "seg-draft": "draft", "seg-exported": "exported" };
  const wantStatus = statusForSeg[documentsState.segment];
  tbody.querySelectorAll("tr").forEach(tr => {
    const status = tr.querySelector("td[data-col=status] .pill")?.textContent?.toLowerCase() || "";
    const name = tr.querySelector(".doc-name__main")?.textContent?.toLowerCase() || "";
    const dossier = tr.querySelector("td[data-col=dossier]")?.textContent?.toLowerCase() || "";
    const matchStatus = !wantStatus || status.includes({"review":"reviewer","anon":"anonymisé","draft":"brouillon","exported":"exporté"}[wantStatus]);
    const matchQuery = !documentsState.query || name.includes(documentsState.query) || dossier.includes(documentsState.query);
    tr.style.display = matchStatus && matchQuery ? "" : "none";
  });
}
```

- [ ] **Step 2: Manual verification**

Reload, click "À reviewer" segment — only review rows visible. Type "Martin" in search — only Martin rows. Click "Tous" — all rows back.

- [ ] **Step 3: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat(redesign): segment + search filter for documents list"
```

---

## Phase 5 · Document détail (revue & anonymisation)

### Task 5.1: Test for redesigned detail panel

**Files:**
- Modify: `tests/api/test_redesign_structure.py`

- [ ] **Step 1: Append failing assertions**

```python
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
    # Privacy lens entry
    assert "data-privacy-lens-toggle" in html
    # Validate button with ⌘↵ hint
    assert "⌘↵" in html or "⌘ ↵" in html or "Cmd+↵" in html
```

Run: expect FAIL.

### Task 5.2: Restructure the anonymization panel into the new detail layout

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/css/screens.css`

- [ ] **Step 1: Replace `<div id="panel-anon">…</div>`**

Replace the entire `panel-anon` block with:

```html
<div id="panel-anon" class="panel" data-document-detail data-privacy-lens="off" data-privacy-zones="[]">
  <header class="detail-topbar">
    <button class="btn-ghost" data-action="back-to-documents">← Documents</button>
    <div class="crumb">
      <span id="detail-dossier-name">—</span>
      <span class="crumb__sep" aria-hidden="true">/</span>
      <span class="crumb__doc" data-active-document id="detail-doc-name">—</span>
    </div>
    <span class="pill pill-review" id="detail-status">À reviewer</span>
    <div class="detail-topbar__actions">
      <button class="btn-ghost" data-action="toggle-mode">Mode : Pseudonymiser ▾</button>
      <button class="btn-ghost" data-privacy-lens-toggle>Privacy Lens <span class="kbd">⌘L</span></button>
      <button class="btn-ghost" data-action="open-export">Exporter…</button>
      <button class="btn-primary-ok" data-action="validate-anonymization">
        ✓ Valider l'anonymisation <span class="kbd">⌘↵</span>
      </button>
    </div>
  </header>

  <div class="detail-grid">
    <section class="pane pane-original" id="pane-original">
      <header class="pane-head"><span class="pane-dot pane-dot--raw"></span> Original <span class="pane-meta" id="pane-original-meta">— pages</span></header>
      <div class="viewer viewer-original" id="original-viewer-container">
        <div id="original-placeholder" class="viewer-placeholder">Chargement du document…</div>
      </div>
      <div class="privacy-lens-overlay"></div>
    </section>

    <section class="pane pane-anonymized" id="pane-anonymized">
      <header class="pane-head"><span class="pane-dot pane-dot--accent"></span> Anonymisé <span class="pane-meta" id="pane-anon-meta">— entités</span></header>
      <div class="viewer viewer-anonymized" id="anonymized-viewer-container">
        <div class="viewer-placeholder">En attente d'anonymisation…</div>
      </div>
    </section>

    <aside class="rail">
      <section class="rail-section" id="rail-trust">
        <h2 class="rail-h">Trust score</h2>
        <trust-gauge id="detail-trust-gauge" data-size="140" data-pii="0" data-quasi="0" data-coherence="0" data-reversibility="0"></trust-gauge>
        <ul class="rail-trust__legend" id="detail-trust-legend"></ul>
      </section>

      <section class="rail-section" id="rail-metadata">
        <h2 class="rail-h">Métadonnées</h2>
        <dl class="meta-list" id="detail-metadata"></dl>
      </section>

      <section class="rail-section" id="rail-copilot">
        <h2 class="rail-h">Copilot IA</h2>
        <div id="detail-copilot-alerts"></div>
        <button class="rail-copilot-ask" data-action="open-copilot">Demander au Copilot… <span class="kbd">⌘J</span></button>
      </section>

      <section class="rail-section" id="rail-audit">
        <h2 class="rail-h">Audit (extraits)</h2>
        <ol class="audit-log" id="detail-audit-log"></ol>
      </section>
    </aside>
  </div>

  <footer class="detail-actionbar">
    <span class="detail-actionbar__summary" id="detail-summary">— entités · — PII résiduel</span>
    <div class="detail-actionbar__actions">
      <button class="btn-ghost" data-action="re-anonymize-strict">Re-anonymiser (règles strictes)</button>
      <button class="btn-ghost" data-action="preview-redacted">Aperçu PDF redacté</button>
      <button class="btn-primary-ok" data-action="validate-anonymization">Valider &amp; exporter</button>
    </div>
  </footer>
</div>
```

- [ ] **Step 2: Style the detail layout**

Append to `app/static/css/screens.css`:

```css
/* Document detail */
.detail-topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  font-size: 12px;
  color: var(--ink-muted);
}
.crumb { display: flex; align-items: center; gap: 6px; }
.crumb__sep { opacity: 0.4; }
.crumb__doc { color: var(--ink); font-weight: 600; }
.detail-topbar__actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 320px;
  min-height: calc(100vh - 200px);
}
.pane {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  position: relative;
}
.pane:last-child { border-right: 0; }
.pane-head {
  padding: 9px 14px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  font-weight: 700;
  color: var(--ink-muted);
  display: flex;
  align-items: center;
  gap: 8px;
}
.pane-dot { width: 7px; height: 7px; border-radius: 50%; }
.pane-dot--raw { background: var(--raw); }
.pane-dot--accent { background: var(--accent); }
.pane-meta { margin-left: auto; font-weight: 500; text-transform: none; letter-spacing: 0; color: var(--ink-dim); font-size: 11px; }

.viewer { flex: 1; padding: 22px 26px; font-size: 13px; line-height: 1.75; color: var(--ink); overflow: auto; }
.viewer-original { background: var(--raw-soft); }
.viewer-anonymized { background: var(--surface-2); }

.rail { background: var(--surface); padding: 16px 18px; overflow: auto; }
.rail-section { margin-bottom: 22px; }
.rail-h { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700; color: var(--ink-muted); margin: 0 0 10px; }
.meta-list { font-size: 12px; margin: 0; padding: 0; }
.meta-list .row { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--border); }
.meta-list .row:last-child { border-bottom: 0; }
.meta-list dt { color: var(--ink-muted); }
.meta-list dd { color: var(--ink); font-weight: 500; margin: 0; text-align: right; }

.rail-trust__legend { list-style: none; padding: 0; margin: 12px 0 0; font-size: 12px; }
.rail-trust__legend li { display: flex; align-items: center; gap: 8px; padding: 5px 0; }
.rail-trust__legend .swatch { width: 8px; height: 8px; border-radius: 2px; }
.rail-trust__legend .leg-val { margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 700; color: var(--ink); }

.audit-log { list-style: none; padding: 0; margin: 0; font-size: 12px; }
.audit-log li { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); }
.audit-log li:last-child { border-bottom: 0; }
.audit-log .ts { color: var(--ink-dim); font-variant-numeric: tabular-nums; width: 50px; flex-shrink: 0; font-size: 11px; }
.audit-log .what { color: var(--ink-2); line-height: 1.5; }
.audit-log .what strong { color: var(--ink); font-weight: 600; }

.detail-actionbar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 22px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}
.detail-actionbar__summary { font-size: 12px; color: var(--ink-muted); }
.detail-actionbar__summary strong { color: var(--ink); font-weight: 600; }
.detail-actionbar__actions { margin-left: auto; display: flex; gap: 8px; }
```

- [ ] **Step 3: Update existing handlers**

Where the legacy code references the old IDs (`anon-toolbar`, `tab-original`, etc.), keep the renders attached to the new `id="original-viewer-container"` / `id="anonymized-viewer-container"`. Do a quick check:

```bash
grep -n "anon-toolbar\|tab-original\|anon-preview" app/static/js/app.js | head -20
```

For each match: either remove the line (the feature is replaced by the new layout) or rebind to the new IDs. If unsure, comment out the line with `// MIGRATED-OUT: replaced by detail-grid in Phase 5`.

- [ ] **Step 4: Run the detail test**

Run: `pytest tests/api/test_redesign_structure.py -v -k "document_detail_layout"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html app/static/css/screens.css app/static/js/app.js
git commit -m "feat(redesign): document detail with dual pane + trust rail"
```

### Task 5.3: Wire the Trust Gauge legend dynamically

**Files:**
- Modify: `app/static/js/app.js`

- [ ] **Step 1: Add a helper**

```js
function renderTrustLegend(values) {
  const ul = document.getElementById("detail-trust-legend");
  if (!ul) return;
  const colorFor = v => v >= 90 ? "var(--accent)" : v >= 70 ? "var(--warning)" : "var(--danger)";
  const rows = [
    { k: "pii",           label: "PII directs" },
    { k: "quasi",         label: "Quasi-identifiants" },
    { k: "coherence",     label: "Cohérence tokens" },
    { k: "reversibility", label: "Réversibilité" },
  ];
  ul.innerHTML = rows.map(r => {
    const v = values[r.k] ?? 0;
    return `<li><span class="swatch" style="background:${colorFor(v)}"></span>
      <span class="leg-lbl">${r.label}</span><span class="leg-val">${v}%</span></li>`;
  }).join("");
}
```

- [ ] **Step 2: Call `renderTrustLegend` whenever a doc is opened**

Find the function that loads document details (search `open-doc` or the legacy anon-panel opener). After setting trust gauge attributes:

```js
const gauge = document.getElementById("detail-trust-gauge");
const values = { pii: doc.pii ?? 0, quasi: doc.quasi ?? 0, coherence: doc.coherence ?? 0, reversibility: doc.reversibility ?? 0 };
Object.entries(values).forEach(([k, v]) => gauge.setAttribute(`data-${k}`, v));
renderTrustLegend(values);
```

- [ ] **Step 3: Manual verification**

Open a document. Expected: gauge animates to its values, legend lists 4 dimensions with correct colors.

- [ ] **Step 4: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat(redesign): trust gauge legend on document detail"
```

### Task 5.4: Render anonymized tokens as `.token-card`

**Files:**
- Modify: `app/static/js/app.js`

- [ ] **Step 1: Locate the anonymized text renderer**

```bash
grep -n "anonymized.*text\|interactive-text\|\\[PERSONNE\\|tokens-replace" app/static/js/app.js | head -10
```

- [ ] **Step 2: Wrap token replacements with the new class**

Find the function that converts plain `[PERSONNE_1]` style tokens into HTML. Update it to emit:

```js
function tokenizeAnonymizedHtml(text, mapping) {
  return text.replace(/\[(PERSONNE|ADRESSE|EMAIL|TELEPHONE|IBAN|SIRET|DATE|ENTREPRISE)_(\d+)\]/g, (m, kind, n) => {
    const safe = `${kind}_${n}`;
    return `<span class="token-card" data-token="${safe}" tabindex="0" role="button" aria-label="Token ${safe} — cliquer pour modifier">[${m.slice(1, -1)}]</span>`;
  });
}
```

Call this from wherever the anonymized text is set into `#anonymized-viewer-container`.

- [ ] **Step 3: Click handler to allow inline edit**

```js
document.getElementById("anonymized-viewer-container")?.addEventListener("click", e => {
  const tok = e.target.closest(".token-card");
  if (!tok) return;
  tok.setAttribute("aria-pressed", "true");
  // Inline edit: replace the chip with a small input
  const original = tok.textContent;
  const input = document.createElement("input");
  input.className = "input";
  input.style.width = "180px";
  input.value = original;
  input.addEventListener("blur", () => commitTokenEdit(tok, input));
  input.addEventListener("keydown", e2 => { if (e2.key === "Enter") input.blur(); if (e2.key === "Escape") cancelTokenEdit(tok, input, original); });
  tok.replaceWith(input);
  input.focus();
  input.select();
});

function commitTokenEdit(tok, input) {
  const newCard = document.createElement("span");
  newCard.className = "token-card";
  newCard.dataset.token = tok.dataset.token;
  newCard.tabIndex = 0;
  newCard.textContent = input.value;
  input.replaceWith(newCard);
  // Persistence: if window.confidocPersistTokenOverride exists (added by a separate
  // backend task — out of scope here per spec §9), call it; otherwise edit stays client-side only.
  window.confidocPersistTokenOverride?.(newCard.dataset.token, newCard.textContent);
}
function cancelTokenEdit(tok, input, original) { tok.textContent = original; input.replaceWith(tok); }
```

- [ ] **Step 4: Manual verification**

Open a document with detected entities. Expected: each `[PERSONNE_1]` etc. appears as an emerald token-card. Click → input appears for inline edit. Esc cancels, Enter commits.

- [ ] **Step 5: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat(signature): inline-editable token cards in detail view"
```

### Task 5.5: Wire the Validate button to Scan Reveal

**Files:**
- Modify: `app/static/js/app.js`

- [ ] **Step 1: Update the click handler for `data-action="validate-anonymization"`**

```js
document.addEventListener("click", async e => {
  const btn = e.target.closest('[data-action="validate-anonymization"]');
  if (!btn) return;
  e.preventDefault();
  const panel = document.getElementById("panel-anon");
  if (!panel) return;
  // Run the actual validation API call first (re-use existing handler)
  try {
    await window.confidocValidateAnonymization?.();
  } catch (err) { console.error(err); return; }
  // Then the ceremony
  const { triggerScanReveal } = await import("/static/js/components/scan-reveal.js");
  await triggerScanReveal(panel.querySelector(".detail-grid"));
});
```

If `window.confidocValidateAnonymization` does not exist, alias the existing validate function: at the top of the existing validate routine, add `window.confidocValidateAnonymization = validate;` (or whatever the function is named).

- [ ] **Step 2: Keyboard shortcut ⌘↵**

```js
document.addEventListener("keydown", e => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    const validateBtn = document.querySelector('#panel-anon [data-action="validate-anonymization"]');
    if (validateBtn && document.getElementById("panel-anon")?.classList.contains("is-active")) {
      e.preventDefault();
      validateBtn.click();
    }
  }
});
```

- [ ] **Step 3: Manual verification**

Open a document. Click "Valider l'anonymisation" (or press ⌘↵). Expected: API call runs, then the emerald line sweeps the detail grid in 600ms, then a check appears.

- [ ] **Step 4: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat(signature): scan reveal on anonymization validate"
```

---

## Phase 6 · Accueil refactor

### Task 6.1: Test for the new Accueil structure

**Files:**
- Modify: `tests/api/test_redesign_structure.py`

- [ ] **Step 1: Append failing assertion**

```python
@pytest.mark.anyio
async def test_accueil_uses_hero_literary(client):
    resp = await client.get("/ui")
    html = resp.text
    assert 'class="hero-literary"' in html
    assert 'id="home-priority-list"' in html
    assert 'id="home-timeline"' in html
    assert 'id="home-kpis"' in html
```

Run: expect FAIL.

### Task 6.2: Refactor `panel-dashboard` to the briefing layout

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/css/screens.css`

- [ ] **Step 1: Replace `<div id="panel-dashboard">` content**

```html
<div id="panel-dashboard" class="panel is-active">
  <header class="home-hero">
    <h1 class="hero-literary" id="home-hero">
      Bonjour <span id="home-user-name">—</span>. Aujourd'hui, <em class="literary" id="home-priority-count">— documents</em> attendent ta revue.
    </h1>
    <p class="hero-lead" id="home-hero-lead">Chargement de ton briefing…</p>
  </header>

  <section class="home-section">
    <h2 class="section-title">À reviewer en premier</h2>
    <ol class="priority-list" id="home-priority-list"></ol>
  </section>

  <section class="home-section">
    <h2 class="section-title">Activité du jour</h2>
    <div class="timeline" id="home-timeline"></div>
  </section>

  <section class="home-section">
    <h2 class="section-title">Vue d'ensemble</h2>
    <div class="kpis" id="home-kpis"></div>
  </section>
</div>
```

- [ ] **Step 2: Style the Accueil**

Append to `screens.css`:

```css
.home-hero { margin-bottom: 28px; }
.home-section { margin-bottom: 28px; }
.section-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 700;
  color: var(--ink-muted);
  margin: 0 0 12px;
}
.priority-list { list-style: none; padding: 0; margin: 0; border: 1px solid var(--border); border-radius: var(--r-xl); overflow: hidden; }
.priority-list li {
  display: grid;
  grid-template-columns: 48px 1fr auto auto;
  gap: 14px;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-2);
}
.priority-list li:last-child { border-bottom: 0; }
.priority-list .name { font-weight: 500; }
.priority-list .meta { font-size: 11px; color: var(--ink-dim); }

.timeline { font-size: 13px; line-height: 1.75; color: var(--ink-2); padding: 0; }
.timeline .ev { padding-right: 14px; }
.timeline .ts { font-variant-numeric: tabular-nums; color: var(--ink-dim); }

.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
```

- [ ] **Step 3: Render data**

In `app.js`, locate the dashboard fetch (search `panel-dashboard` or `dashboard` API). Replace its rendering with:

```js
function renderHome(data) {
  const user = data.user_name || "Grégory";
  document.getElementById("home-user-name").textContent = user;
  const pri = data.priority_docs || [];
  document.getElementById("home-priority-count").textContent = `${pri.length} document${pri.length>1?"s":""}`;
  document.getElementById("home-hero-lead").textContent = pri.length
    ? "Trois bilans sont sous la barre des 90% de confiance."
    : "Aucun document n'attend ta revue.";

  const list = document.getElementById("home-priority-list");
  list.innerHTML = pri.slice(0, 5).map(d => `
    <li>
      <trust-gauge data-mini="true" data-size="40"
        data-pii="${d.pii ?? 0}" data-quasi="${d.quasi ?? 0}"
        data-coherence="${d.coherence ?? 0}" data-reversibility="${d.reversibility ?? 0}"></trust-gauge>
      <div>
        <div class="name">${escapeHtml(d.name)}</div>
        <div class="meta">${escapeHtml(d.dossier || "—")} · ${d.uploaded_ago || "—"}</div>
      </div>
      <span class="pill pill-review">À reviewer</span>
      <button class="btn-ghost" data-action="open-doc" data-doc-id="${d.id}">▶ Reviewer</button>
    </li>
  `).join("");

  document.getElementById("home-timeline").innerHTML = (data.timeline || []).map(ev =>
    `<div class="ev"><span class="ts">${ev.ts}</span> · ${escapeHtml(ev.text)}</div>`).join("");

  document.getElementById("home-kpis").innerHTML = (data.kpis || []).map(k => `
    <div class="card kpi-card ${k.variant === "trust" ? "kpi-card--trust" : ""}">
      <div class="kpi-label">${escapeHtml(k.label)}</div>
      <div class="kpi-value tabular">${k.value}</div>
      <div class="kpi-delta ${k.delta_kind === "warning" ? "is-warning" : ""}">${escapeHtml(k.delta)}</div>
    </div>
  `).join("");
}

window.renderHome = renderHome;
```

(If the dashboard API does not yet return `priority_docs`/`timeline` shaped like this, add a small adapter mapping the existing payload to these keys. Backend changes are explicitly out of scope per spec §9 — keep the adapter on the client.)

- [ ] **Step 4: Run the test**

Run: `pytest tests/api/test_redesign_structure.py -v -k "accueil_uses_hero_literary"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html app/static/css/screens.css app/static/js/app.js
git commit -m "feat(redesign): accueil briefing with hero literary, priority list, timeline"
```

---

## Phase 7 · Remaining screens

### Task 7.1: Dossiers list + detail

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/css/screens.css`

- [ ] **Step 1: Replace `<div id="panel-dossier">…</div>`**

Use the same grammar as Documents (panel-head + table). The dossier-detail "tabs" remain but use the new component classes:

```html
<div id="panel-dossier" class="panel">
  <header class="panel-head">
    <div>
      <h1 class="page-title">Dossiers</h1>
      <p class="page-lead" id="dossiers-summary">—</p>
    </div>
    <div class="panel-actions">
      <button class="btn-primary" data-action="new-dossier"><span aria-hidden="true">+</span> Nouveau dossier</button>
    </div>
  </header>

  <div class="filter-bar">
    <input type="search" class="input" id="dossiers-search" placeholder="⌕ Filtrer par nom de client…">
  </div>

  <table class="table" id="dossiers-table">
    <thead>
      <tr><th>Client</th><th>Documents</th><th>Trust moyen</th><th>Dernière activité</th><th>Propriétaire</th></tr>
    </thead>
    <tbody id="dossiers-tbody"></tbody>
  </table>

  <div id="dossier-detail" class="dossier-detail" hidden>
    <header class="panel-head">
      <div>
        <button class="btn-ghost" data-action="back-to-dossiers">← Dossiers</button>
        <h2 class="page-title" id="dossier-detail-name">—</h2>
        <p class="page-lead"><span id="dossier-detail-meta">—</span></p>
      </div>
    </header>
    <div class="segment" id="dossier-detail-tabs">
      <button data-segment="tab-documents" aria-pressed="true">Documents</button>
      <button data-segment="tab-comparison" aria-pressed="false">Comparaison pluri-annuelle</button>
      <button data-segment="tab-metadata" aria-pressed="false">Métadonnées</button>
    </div>
    <div id="dossier-tab-content"></div>
  </div>
</div>
```

- [ ] **Step 2: Wire `data-nav="clients"` → `panel-dossier`**

In `app.js` nav router, ensure clients maps to `panel-dossier`.

- [ ] **Step 3: Commit**

```bash
git add app/templates/index.html app/static/css/screens.css app/static/js/app.js
git commit -m "feat(redesign): dossiers list + detail grammar"
```

### Task 7.2: Qualité & RGPD (fusion of quality + compliance)

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/js/app.js`

- [ ] **Step 1: Replace `<div id="panel-quality">` content**

```html
<div id="panel-quality" class="panel">
  <header class="panel-head">
    <div>
      <h1 class="page-title">Qualité &amp; RGPD</h1>
      <p class="page-lead">Tableau de bord trust pour l'équipe et le DPO.</p>
    </div>
    <div class="panel-actions">
      <button class="btn-ghost" data-action="download-compliance-cert">Télécharger le certificat RGPD</button>
    </div>
  </header>
  <div class="segment" id="quality-tabs">
    <button data-segment="tab-scores" aria-pressed="true">Trust scores</button>
    <button data-segment="tab-rgpd" aria-pressed="false">Conformité RGPD</button>
    <button data-segment="tab-golden" aria-pressed="false">Golden sets</button>
  </div>
  <div id="quality-tab-content"></div>
</div>
```

- [ ] **Step 2: Remove `<div id="panel-compliance">`**

Delete the whole legacy `panel-compliance` block from `index.html`. Update any nav map that referenced it (`data-nav="compliance"` is already removed in Task 3.2).

- [ ] **Step 3: Re-attach the legacy compliance content under the "Conformité RGPD" tab**

Move the previously-inside-`panel-compliance` content under a switch in `app.js`:

```js
function renderQualityTab(tab) {
  const c = document.getElementById("quality-tab-content");
  if (tab === "tab-rgpd") {
    // reuse the markup that used to live in panel-compliance — paste it as a template string here
    c.innerHTML = window.confidocComplianceHtml ?? "<p>Conformité RGPD à charger…</p>";
  } else if (tab === "tab-golden") {
    c.innerHTML = "<p>Golden sets — taux de réussite, dernière exécution.</p>";
  } else {
    c.innerHTML = "<p>Trust scores — distribution du mois, top documents à risque.</p>";
  }
}
```

Plus wire the segment buttons:

```js
document.getElementById("quality-tabs")?.addEventListener("click", e => {
  const b = e.target.closest("[data-segment]"); if (!b) return;
  document.querySelectorAll("#quality-tabs [data-segment]").forEach(x => x.setAttribute("aria-pressed", x === b ? "true" : "false"));
  renderQualityTab(b.dataset.segment);
});
```

- [ ] **Step 4: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat(redesign): merge Qualité & Conformité into single page with tabs"
```

### Task 7.3: Journal d'audit panel

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Replace the placeholder `panel-audit` from Task 3.2**

```html
<div id="panel-audit" class="panel">
  <header class="panel-head">
    <div>
      <h1 class="page-title">Journal d'audit</h1>
      <p class="page-lead">Toutes les actions horodatées sur les documents.</p>
    </div>
    <div class="panel-actions">
      <button class="btn-ghost" data-action="export-audit">Exporter CSV</button>
    </div>
  </header>
  <div class="filter-bar">
    <input type="search" class="input" id="audit-search" placeholder="⌕ Filtrer par utilisateur, document, type d'action…">
    <button class="chip" data-filter="audit-user">Utilisateur ▾</button>
    <button class="chip" data-filter="audit-action">Action ▾</button>
    <button class="chip" data-filter="audit-period">Période ▾</button>
  </div>
  <table class="table" id="audit-table">
    <thead><tr><th>Horodatage</th><th>Utilisateur</th><th>Action</th><th>Objet</th></tr></thead>
    <tbody id="audit-tbody"></tbody>
  </table>
</div>
```

- [ ] **Step 2: Hook the audit fetch**

If a `/api/v1/audit` endpoint exists, call it from `app.js` when `data-nav="audit"` is activated. Otherwise leave a stub that says "Chargement…".

- [ ] **Step 3: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat(redesign): journal d'audit promoted to top-level page"
```

### Task 7.4: Paramètres

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Replace `<div id="panel-settings">…</div>`**

```html
<div id="panel-settings" class="panel">
  <header class="panel-head">
    <div>
      <h1 class="page-title">Paramètres</h1>
      <p class="page-lead">Préférences, anonymisation, équipe.</p>
    </div>
  </header>
  <div class="segment" id="settings-tabs">
    <button data-segment="set-profile" aria-pressed="true">Profil</button>
    <button data-segment="set-appearance" aria-pressed="false">Apparence</button>
    <button data-segment="set-anonymization" aria-pressed="false">Anonymisation</button>
    <button data-segment="set-copilot" aria-pressed="false">Copilot</button>
    <button data-segment="set-api" aria-pressed="false">API &amp; intégrations</button>
    <button data-segment="set-team" aria-pressed="false">Équipe</button>
  </div>
  <div id="settings-tab-content">
    <p class="page-lead">Sélectionne un onglet pour afficher les paramètres.</p>
  </div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/index.html
git commit -m "feat(redesign): paramètres skeleton with 6 tabs"
```

---

## Phase 8 · Copilot drawer migration

### Task 8.1: Move `panel-ai` content into the drawer

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/js/app.js`
- Modify: `app/static/js/components/drawer.js`

- [ ] **Step 1: Locate `panel-ai`**

```bash
grep -n 'id="panel-ai"' app/templates/index.html
```

- [ ] **Step 2: Extract the panel's interactive content into a template**

In `index.html`, replace `panel-ai`'s body with a `<template>` tag that the drawer will clone:

```html
<template id="tmpl-copilot">
  <!-- Move all the original panel-ai children here, unchanged -->
</template>
```

Keep the existing `id="panel-ai"` wrapper but make it an empty div with `hidden` attribute (preserves any straggling JS references).

- [ ] **Step 3: Drawer clones the template on open**

Replace `populate(body)` in `drawer.js`:

```js
function populate(body) {
  const tmpl = document.getElementById("tmpl-copilot");
  body.innerHTML = "";
  if (tmpl) body.appendChild(tmpl.content.cloneNode(true));
  const docName = document.querySelector("[data-active-document]")?.textContent?.trim();
  if (docName) {
    const ctx = document.createElement("p");
    ctx.style.cssText = "margin:0 0 12px;font-size:12px;color:var(--ink-muted)";
    ctx.innerHTML = `Contexte : <strong>${docName}</strong>`;
    body.prepend(ctx);
  }
}
```

- [ ] **Step 4: Update the test_ui_routes assertion**

`test_console_ui_shell_stays_self_hosted_and_well_formed` asserts `panel_ai = resp.text.index('<div id="panel-ai"' …)` and that it is inside `<main>`. Keep the empty wrapper so that assertion continues to pass. If the test still fails, update its assertion to look for `<template id="tmpl-copilot"` *inside* `<main>` instead — and update the test in the same commit.

Run: `pytest tests/api/test_ui_routes.py::test_console_ui_shell_stays_self_hosted_and_well_formed -v`
Expected: PASS (possibly after updating the test).

- [ ] **Step 5: Manual verification**

Reload `/ui`. Press ⌘J. Expected: drawer opens with the Copilot UI inside (questions, summary buttons, etc.) — same controls as the old panel.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html app/static/js/app.js app/static/js/components/drawer.js tests/api/test_ui_routes.py
git commit -m "feat(redesign): move panel-ai into ⌘J drawer template"
```

---

## Phase 9 · Cleanup

### Task 9.1: Delete legacy CSS sections

**Files:**
- Modify: `app/static/css/style.css`

- [ ] **Step 1: Identify legacy sections**

```bash
grep -n "indigo\|violet\|--grad-brand\|--grad-glow\|--accent-glow\|glassmorphism\|var(--glass)" app/static/css/style.css | head -20
```

- [ ] **Step 2: For each rule, decide: keep or delete**

Delete any rule whose selectors are no longer referenced in the DOM (use `grep -r "selector" app/templates app/static/js` to confirm). Examples to delete:

- `--grad-brand`, `--grad-surface`, `--grad-glow`, `--accent-glow` token definitions
- `backdrop-filter: var(--glass)` rules
- Old `--bg-card: rgba(13, 13, 24, 0.92)` etc. (overridden by `tokens.css` anyway)
- `--accent-light: #a855f7` and any rule using it

For every deletion, run:

```bash
grep -rn "<deleted-selector>" app/
```

to confirm zero hits before removing.

- [ ] **Step 3: Verify smoke tests still pass**

Run: `pytest tests/api/ -v`
Expected: all green.

- [ ] **Step 4: Measure CSS size**

Run: `wc -l app/static/css/*.css`
Target: total < 3 000 lines (spec §10 criterion 12).

- [ ] **Step 5: Commit**

```bash
git add app/static/css/
git commit -m "chore(redesign): delete legacy indigo-violet/glassmorphism CSS"
```

### Task 9.2: Remove the dev-test static mount

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Remove the conditional `CONFIDOC_DEV_TESTS` static mount**

Delete the block added in Task 2.2 Step 3. The unit-test HTML pages are still useful when launching with the same env var, but we don't want it shipped to prod unconditionally — and the block is already env-gated, so this is just cleanup if you decide it's no longer needed.

(Skip this task if you want to keep the dev mount.)

- [ ] **Step 2: Commit (if step 1 executed)**

```bash
git add app/main.py
git commit -m "chore(redesign): drop dev-only tests-static mount"
```

### Task 9.3: Final smoke + golden run

**Files:**
- (no edits)

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/ -v --no-header
```

Expected: all green, including:
- `test_ui_routes.py` (legacy)
- `test_redesign_structure.py` (new)
- `test_documents_api.py`, `test_dossiers_api.py`, etc.

If anything fails, fix in the same commit cycle. Do not move on with red tests.

- [ ] **Step 2: Run the golden set**

```bash
pytest tests/unit/test_anonymization_regression_b2b.py -v
```

Expected: pass (no backend regression).

- [ ] **Step 3: Manual walk-through**

In a browser at `/ui`:
1. Login → Accueil (Hero literary visible)
2. ⌘K → palette opens, "doc" filters
3. Navigate to Documents → segments work, search works, mini Trust Gauges render
4. Click ▶ Reviewer on a document → detail screen with 3 panes
5. Click an `[PERSONNE_1]` token → inline edit
6. ⌘L → Privacy Lens overlay appears on Original pane
7. ⌘J → Copilot drawer opens
8. Click Valider l'anonymisation → scan reveal then check
9. Navigate to Qualité & RGPD, Journal d'audit, Paramètres → all render

If any step fails, file an issue and fix before marking the plan complete.

- [ ] **Step 4: Final commit**

```bash
git commit --allow-empty -m "chore(redesign): plan complete — all smoke + golden tests green"
```

---

## Self-review summary

**Spec coverage:**
- §2 direction & principles → Phase 1 (tokens), Phase 2 (signatures)
- §3 design tokens → Phase 1 Tasks 1.1–1.5
- §3.5 signature layer → Phase 2 Tasks 2.1–2.7
- §4 navigation → Phase 3 Tasks 3.1–3.3
- §5.1 Accueil → Phase 6
- §5.2 Documents list → Phase 4
- §5.3 Document détail → Phase 5
- §5.4 Dossiers → Phase 7 Task 7.1
- §5.5 Qualité & RGPD → Phase 7 Task 7.2
- §5.6 Journal d'audit → Phase 7 Task 7.3
- §5.7 Paramètres → Phase 7 Task 7.4
- §6 omniprésents → Tasks 2.6 (⌘K), 2.7 (⌘J), 5.5 (⌘↵), 2.5 (⌘L)
- §7 accessibilité → Task 1.3 (skip-link, prefers-reduced-motion, focus-visible)
- §7bis animations → Tasks 1.2 (motion tokens), 2.2 (gauge), 2.4 (scan), all transition uses `--t-fast`
- §7ter responsive → not explicitly tasked; the desktop-first scope is preserved (the legacy mobile guardrail already exists in `style.css` — verify in Task 9.1)
- §8 migration → exactly Phases 0–9
- §10 validation → covered by Task 9.3 walkthrough + tests

**Placeholders:** No "TBD"/"TODO" in any task body. Every code-changing step shows the code or the exact diff target.

**Type/identifier consistency:** All `data-nav` keys match between sidebar (Task 3.2), router (Task 4.2 Step 5), command palette (Task 2.6), and tests (Task 3.1). Custom element name `<trust-gauge>` is consistent (Tasks 2.2, 4.3, 6.2). The attribute name `data-document-detail` is consistent (Tasks 5.2, 2.5).
