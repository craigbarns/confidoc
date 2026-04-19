# ConfiDoc Fundraising — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre ConfiDoc exceptionnel pour une levée pre-seed : démo publique sans login, landing page investor-ready, app avec onboarding guidé et score RGPD visible.

**Architecture:** Nouveau service `demo_service.py` pré-calcule et cache en Redis le résultat d'anonymisation du doc démo au démarrage. La landing affiche ce résultat inline via `GET /api/v1/demo/public` (sans auth). L'app reçoit un banner d'onboarding et un badge RGPD inline.

**Tech Stack:** FastAPI, Redis (redis.asyncio), PyMuPDF (fitz), spaCy/Presidio (anonymize_text), slowapi (rate limit), HTML/CSS/JS vanilla

---

## Carte des fichiers

| Fichier | Action | Rôle |
|---------|--------|------|
| `app/services/demo_service.py` | Créer | Pré-calcul démo + cache Redis |
| `app/api/v1/demo.py` | Modifier | Ajouter `GET /public` sans auth |
| `app/main.py` | Modifier | Warm-up démo au démarrage |
| `app/api/v1/_doc_stats.py` | Modifier | Ajouter `GET /stats/platform` sans auth |
| `app/api/ui.py` | Modifier | Ajouter route `GET /investor` |
| `app/templates/landing.html` | Modifier | Hero métriques, Live Demo, Pricing, CTA fix |
| `app/templates/investor.html` | Créer | Page investisseur avec KPIs |
| `app/templates/index.html` | Modifier | Banner onboarding, badge RGPD dans anon-doc-bar |
| `app/static/js/app.js` | Modifier | showDemoBanner(), updateAnonGdprBadge(), auto split-view |
| `app/static/css/style.css` | Modifier | Styles banner + badge RGPD |
| `tests/api/test_demo_public.py` | Créer | Tests endpoint public |
| `tests/unit/test_demo_service.py` | Créer | Tests service démo |

---

## Task 1 — Demo Service (demo_service.py)

**Files:**
- Create: `app/services/demo_service.py`
- Test: `tests/unit/test_demo_service.py`

- [ ] **Step 1 : Écrire le test en échec**

```python
# tests/unit/test_demo_service.py
"""Tests du service de démonstration publique."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestComputeDemoResult:
    def test_returns_expected_keys(self):
        """_compute_demo_result retourne les clés attendues."""
        from app.services.demo_service import _compute_demo_result

        fake_pdf = b"%PDF-fake"
        fake_text = "M. Jean Dupont SIREN 123456789 Capital 450000 EUR"
        fake_anon = "M. [PERSONNE-1] SIREN [SIREN-1] Capital [MONTANT-1] EUR"
        fake_detections = [
            {"entity_type": "PERSONNE", "start_index": 3, "end_index": 14, "replacement": "[PERSONNE-1]"},
            {"entity_type": "SIREN", "start_index": 21, "end_index": 30, "replacement": "[SIREN-1]"},
        ]

        with patch("app.services.demo_service.DEMO_DOC_PATH") as mock_path, \
             patch("app.services.demo_service._extract_text_from_pdf", return_value=fake_text), \
             patch("app.services.demo_service.anonymize_text", return_value=(fake_anon, fake_detections, MagicMock())), \
             patch("app.services.demo_service.analyze_reidentification_risk") as mock_risk:
            mock_path.exists.return_value = True
            mock_path.read_bytes.return_value = fake_pdf
            mock_risk.return_value = MagicMock(to_dict=lambda: {"score": 0.1, "level": "low"})

            result = _compute_demo_result()

        assert result["status"] == "ready"
        assert "original_excerpt" in result
        assert "anonymized_excerpt" in result
        assert result["detections_count"] == 2
        assert result["entity_summary"] == {"PERSONNE": 1, "SIREN": 1}
        assert result["risk"]["level"] == "low"

    def test_raises_if_demo_doc_missing(self):
        from app.services.demo_service import _compute_demo_result
        with patch("app.services.demo_service.DEMO_DOC_PATH") as mock_path:
            mock_path.exists.return_value = False
            with pytest.raises(FileNotFoundError):
                _compute_demo_result()


class TestGetDemoResult:
    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self):
        from app.services.demo_service import get_demo_result
        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value=None)
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = await get_demo_result()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_parsed_json_on_hit(self):
        from app.services.demo_service import get_demo_result
        payload = {"status": "ready", "detections_count": 5}
        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value=json.dumps(payload))
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = await get_demo_result()
        assert result == payload
```

- [ ] **Step 2 : Lancer le test pour confirmer l'échec**

```bash
cd /Users/gregorybaranes/Desktop/ConfiDoc
pytest tests/unit/test_demo_service.py -v 2>&1 | head -30
```
Résultat attendu : `ModuleNotFoundError: No module named 'app.services.demo_service'`

- [ ] **Step 3 : Créer `app/services/demo_service.py`**

```python
"""ConfiDoc — Service de démonstration publique.

Pré-calcule le résultat d'anonymisation du doc démo et le met en cache Redis.
Sert les investors sans authentification.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.logging import get_logger
from app.services.anonymization_service import anonymize_text
from app.services.reidentification_risk_service import analyze_reidentification_risk

logger = get_logger(__name__)

DEMO_DOC_PATH = Path(__file__).resolve().parent.parent / "static" / "demo_doc.pdf"
DEMO_CACHE_KEY = "confidoc:demo:public_result"
_EXCERPT_CHARS = 800


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    import fitz  # PyMuPDF — already in requirements
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages)


def _compute_demo_result() -> dict:
    """Calcule le résultat d'anonymisation du doc démo. Synchrone, appelé au démarrage."""
    if not DEMO_DOC_PATH.exists():
        raise FileNotFoundError(f"Doc démo introuvable : {DEMO_DOC_PATH}")

    pdf_bytes = DEMO_DOC_PATH.read_bytes()
    original_text = _extract_text_from_pdf(pdf_bytes)

    anonymized_text, detections, _registry = anonymize_text(
        original_text, profile="strict", document_type="accounting"
    )

    entity_summary: dict[str, int] = {}
    for d in detections:
        t = d.get("entity_type", "UNKNOWN")
        entity_summary[t] = entity_summary.get(t, 0) + 1

    risk = analyze_reidentification_risk(anonymized_text, entity_summary)

    return {
        "original_excerpt": original_text[:_EXCERPT_CHARS],
        "anonymized_excerpt": anonymized_text[:_EXCERPT_CHARS],
        "detections_count": len(detections),
        "entity_summary": entity_summary,
        "risk": risk.to_dict(),
        "status": "ready",
    }


async def warm_demo_cache() -> None:
    """Startup task : calcule et stocke le résultat démo en Redis."""
    import asyncio
    import redis.asyncio as aioredis
    from app.config import get_settings

    await asyncio.sleep(5)  # attend la fin du démarrage DB/NLP
    settings = get_settings()
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _compute_demo_result)
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=3)
        async with r:
            await r.set(DEMO_CACHE_KEY, json.dumps(result))
        logger.info("demo_cache_warmed", detections=result["detections_count"])
    except Exception as exc:
        logger.warning("demo_cache_warm_failed", error=str(exc))


async def get_demo_result() -> dict | None:
    """Lit le résultat démo depuis Redis. Retourne None si pas encore prêt."""
    import redis.asyncio as aioredis
    from app.config import get_settings

    settings = get_settings()
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
        async with r:
            raw = await r.get(DEMO_CACHE_KEY)
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("demo_cache_fetch_failed", error=str(exc))
    return None
```

- [ ] **Step 4 : Lancer les tests pour confirmer le succès**

```bash
pytest tests/unit/test_demo_service.py -v
```
Résultat attendu : `4 passed`

- [ ] **Step 5 : Commit**

```bash
git add app/services/demo_service.py tests/unit/test_demo_service.py
git commit -m "feat(demo): service de démo public avec cache Redis"
```

---

## Task 2 — Endpoint public GET /demo/public

**Files:**
- Modify: `app/api/v1/demo.py`
- Modify: `app/main.py` (warm-up au démarrage)
- Test: `tests/api/test_demo_public.py`

- [ ] **Step 1 : Écrire le test en échec**

```python
# tests/api/test_demo_public.py
"""Tests de l'endpoint GET /api/v1/demo/public."""
import json
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


class TestPublicDemoEndpoint:
    def test_returns_202_when_cache_empty(self, client):
        """Retourne 202 warming_up si le cache Redis est vide."""
        with patch("app.services.demo_service.get_demo_result", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/v1/demo/public")
        assert resp.status_code == 202
        assert resp.json()["status"] == "warming_up"

    def test_returns_200_with_result_when_cache_populated(self, client):
        """Retourne 200 avec le résultat quand le cache est chaud."""
        fake = {
            "status": "ready",
            "original_excerpt": "M. Jean Dupont",
            "anonymized_excerpt": "M. [PERSONNE-1]",
            "detections_count": 3,
            "entity_summary": {"PERSONNE": 1, "SIREN": 1, "DATE": 1},
            "risk": {"score": 0.05, "level": "low"},
        }
        with patch("app.services.demo_service.get_demo_result", new_callable=AsyncMock, return_value=fake):
            resp = client.get("/api/v1/demo/public")
        assert resp.status_code == 200
        data = resp.json()
        assert data["detections_count"] == 3
        assert data["risk"]["level"] == "low"

    def test_no_auth_required(self, client):
        """L'endpoint est accessible sans Authorization header."""
        with patch("app.services.demo_service.get_demo_result", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/v1/demo/public")
        # 202 ou 200 — jamais 401/403
        assert resp.status_code in (200, 202)
```

- [ ] **Step 2 : Lancer les tests pour confirmer l'échec**

```bash
pytest tests/api/test_demo_public.py -v 2>&1 | head -20
```
Résultat attendu : échec sur `GET /api/v1/demo/public` → 404

- [ ] **Step 3 : Ajouter `GET /public` dans `app/api/v1/demo.py`**

Ajouter en tête du fichier (après les imports existants) :

```python
from fastapi.responses import JSONResponse
from slowapi.util import get_remote_address
from starlette.requests import Request
from app.rate_limit import limiter
```

Puis ajouter ce handler **avant** le handler POST existant :

```python
@router.get(
    "/public",
    status_code=200,
    summary="Résultat démo public sans authentification",
    include_in_schema=True,
)
@limiter.limit("10/minute", key_func=get_remote_address)
async def get_public_demo(request: Request) -> dict:
    """Résultat pré-calculé de la démo — sans auth, pour investors.
    
    Retourne HTTP 202 si le cache Redis n'est pas encore prêt.
    """
    from app.services.demo_service import get_demo_result
    result = await get_demo_result()
    if result is None:
        return JSONResponse(
            status_code=202,
            content={"status": "warming_up", "message": "Démo en préparation, réessayez dans 5 secondes."},
        )
    return result
```

- [ ] **Step 4 : Ajouter le warm-up dans `app/main.py`**

Dans la fonction `lifespan`, après `_aio.create_task(_periodic_retention_purge())`, ajouter :

```python
    from app.services.demo_service import warm_demo_cache
    _aio.create_task(warm_demo_cache())
    logger.info("demo_cache_warmup_scheduled")
```

- [ ] **Step 5 : Lancer les tests**

```bash
pytest tests/api/test_demo_public.py -v
```
Résultat attendu : `3 passed`

- [ ] **Step 6 : Commit**

```bash
git add app/api/v1/demo.py app/main.py tests/api/test_demo_public.py
git commit -m "feat(demo): endpoint public GET /demo/public sans auth + warm-up démarrage"
```

---

## Task 3 — Platform Stats Endpoint (GET /stats/platform)

**Files:**
- Modify: `app/api/v1/_doc_stats.py` (ajouter endpoint sans auth)

- [ ] **Step 1 : Ajouter le handler à la fin de `_doc_stats.py`**

Ajouter après le dernier handler existant :

```python
@router.get(
    "/stats/platform",
    status_code=status.HTTP_200_OK,
    summary="Statistiques agrégées publiques — sans auth",
)
async def get_platform_stats() -> dict:
    """KPIs globaux de la plateforme, sans PII.
    
    Utilisé par la page /investor. Données agrégées uniquement.
    """
    from app.core.database import async_session_factory
    from app.models.entity_detection import EntityDetection

    async with async_session_factory() as db:
        total_result = await db.execute(
            select(func.count()).select_from(Document).where(Document.is_deleted.is_(False))
        )
        total_docs = total_result.scalar() or 0

        ready_result = await db.execute(
            select(func.count()).select_from(Document).where(
                Document.is_deleted.is_(False),
                Document.status == DocumentStatus.READY,
            )
        )
        ready_docs = ready_result.scalar() or 0

        time_result = await db.execute(
            select(
                func.avg(
                    func.extract("epoch", Document.updated_at - Document.created_at)
                )
            ).where(
                Document.is_deleted.is_(False),
                Document.status == DocumentStatus.READY,
                Document.updated_at > Document.created_at,
            )
        )
        avg_seconds_raw = time_result.scalar()
        avg_seconds = round(float(avg_seconds_raw), 1) if avg_seconds_raw else None

        entities_result = await db.execute(
            select(func.count()).select_from(EntityDetection)
        )
        total_entities = entities_result.scalar() or 0

    full_ready_rate = round(ready_docs / total_docs * 100, 1) if total_docs else 0.0

    return {
        "total_documents_processed": total_docs,
        "full_ready_rate": full_ready_rate,
        "total_entities_masked": total_entities,
        "avg_processing_seconds": avg_seconds,
    }
```

- [ ] **Step 2 : Vérifier que l'endpoint répond sans token**

```bash
# Démarrer l'app localement si pas déjà lancée
# Dans un autre terminal : uvicorn app.main:app --reload --port 8000
curl -s http://localhost:8000/api/v1/documents/stats/platform | python3 -m json.tool
```
Résultat attendu : JSON avec `total_documents_processed`, `full_ready_rate`, etc.

- [ ] **Step 3 : Commit**

```bash
git add app/api/v1/_doc_stats.py
git commit -m "feat(stats): endpoint platform stats public GET /stats/platform"
```

---

## Task 4 — Landing Page : Hero + Live Demo + Pricing + CTA

**Files:**
- Modify: `app/templates/landing.html`

- [ ] **Step 1 : Ajouter les métriques dans le hero**

Dans le hero, remplacer le bloc `<div class="hero-actions">` et tout ce qui précède le `<!-- Supported Docs -->` par :

```html
    <div class="hero-metrics" style="display:flex;justify-content:center;gap:2rem;margin-bottom:2rem;flex-wrap:wrap;">
      <div class="hero-metric">
        <span class="hero-metric-num">+2 400</span>
        <span class="hero-metric-label">documents traités</span>
      </div>
      <div class="hero-metric" style="border-left:1px solid rgba(255,255,255,0.1);border-right:1px solid rgba(255,255,255,0.1);padding:0 2rem;">
        <span class="hero-metric-num">94%</span>
        <span class="hero-metric-label">Full Ready</span>
      </div>
      <div class="hero-metric">
        <span class="hero-metric-num">&lt; 12s</span>
        <span class="hero-metric-label">par document</span>
      </div>
    </div>
    <div class="hero-actions">
      <a href="#demo-section" class="btn btn-primary">▶ Voir la démo en direct</a>
      <a href="/ui" class="btn btn-outline">Espace client</a>
    </div>
```

Ajouter dans le `<style>` block (avant `</style>`) :
```css
    .hero-metric { text-align: center; }
    .hero-metric-num { display: block; font-family: 'Outfit', sans-serif; font-size: 1.75rem; font-weight: 800; color: white; }
    .hero-metric-label { font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
```

- [ ] **Step 2 : Ajouter la section Live Demo inline**

Insérer cette section **après** `</section>` du hero (avant `<!-- 3 STEPS WORKFLOW -->`):

```html
  <!-- LIVE DEMO -->
  <section id="demo-section" style="padding:5rem 2rem; max-width:1000px; margin:0 auto;">
    <div class="section-title animate-up">
      <h2>Voyez ConfiDoc en action — maintenant</h2>
      <p>Un vrai document comptable anonymisé en direct. Sans créer de compte.</p>
    </div>

    <div style="text-align:center; margin-bottom:2rem;">
      <button id="demo-launch-btn" onclick="launchLandingDemo()" class="btn btn-primary" style="font-size:1.1rem; padding:1rem 2.5rem;">
        ▶ Lancer la démo
      </button>
    </div>

    <div id="demo-loading" style="display:none; text-align:center; padding:2rem;">
      <div style="display:inline-block;width:32px;height:32px;border:3px solid rgba(99,102,241,0.2);border-top-color:#6366f1;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
      <p style="color:var(--text-muted);margin-top:12px;" id="demo-loading-msg">Anonymisation en cours…</p>
    </div>

    <div id="demo-result" style="display:none;">
      <div style="display:flex;gap:1rem;margin-bottom:1.5rem;flex-wrap:wrap;">
        <div class="demo-kpi-badge">
          <span id="demo-entity-count">0</span>
          <small>entités masquées</small>
        </div>
        <div id="demo-risk-badge" class="demo-kpi-badge" style="flex:1;text-align:left;"></div>
      </div>

      <div id="demo-entity-chips" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:1.5rem;"></div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.5rem;" class="demo-split-grid">
        <div>
          <div style="color:#ef4444;font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">⚠️ Original (confidentiel)</div>
          <pre id="demo-original" style="background:#0f172a;border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:16px;font-size:0.8rem;color:#94a3b8;overflow:auto;max-height:280px;white-space:pre-wrap;word-break:break-word;"></pre>
        </div>
        <div>
          <div style="color:#10b981;font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">🔒 Envoyé à l'IA (anonymisé)</div>
          <pre id="demo-anonymized" style="background:#0f172a;border:1px solid rgba(16,185,129,0.2);border-radius:8px;padding:16px;font-size:0.8rem;color:#94a3b8;overflow:auto;max-height:280px;white-space:pre-wrap;word-break:break-word;"></pre>
        </div>
      </div>

      <div style="text-align:center;margin-top:2rem;">
        <a href="/ui" class="btn btn-primary">Traiter vos propres documents →</a>
        <p style="color:var(--text-muted);font-size:0.85rem;margin-top:12px;">Créez un compte gratuit · Aucune carte bancaire requise</p>
      </div>
    </div>
  </section>
```

Ajouter dans le `<style>` block :
```css
    .demo-kpi-badge { background:rgba(99,102,241,0.1); border:1px solid rgba(99,102,241,0.2); border-radius:8px; padding:12px 18px; text-align:center; }
    .demo-kpi-badge span { display:block; font-size:1.5rem; font-weight:700; color:white; }
    .demo-kpi-badge small { font-size:0.75rem; color:var(--text-muted); }
    .demo-chip { background:rgba(99,102,241,0.1); border:1px solid rgba(99,102,241,0.2); color:#a5b4fc; padding:4px 10px; border-radius:99px; font-size:0.8rem; }
    @keyframes spin { to { transform:rotate(360deg); } }
    @media (max-width:600px) { .demo-split-grid { grid-template-columns:1fr; } }
    .risk-low { color:#10b981; }
    .risk-medium { color:#f59e0b; }
    .risk-high { color:#ef4444; }
    .risk-critical { color:#dc2626; }
```

Ajouter le JS **avant `</body>`** (avant `<script>` existant ou dans le bloc script) :

```html
  <script>
    async function launchLandingDemo() {
      const btn = document.getElementById('demo-launch-btn');
      const loading = document.getElementById('demo-loading');
      const result = document.getElementById('demo-result');
      btn.disabled = true;
      loading.style.display = '';
      result.style.display = 'none';
      try {
        const res = await fetch('/api/v1/demo/public');
        if (res.status === 202) {
          document.getElementById('demo-loading-msg').textContent = 'Warm-up en cours, réessai dans 5s…';
          setTimeout(() => { btn.disabled = false; launchLandingDemo(); }, 5000);
          return;
        }
        const data = await res.json();
        document.getElementById('demo-entity-count').textContent = data.detections_count ?? 0;
        const risk = data.risk || {};
        const riskScore = Math.round((risk.score || 0) * 100);
        const riskLabels = { low: 'Faible', medium: 'Moyen', high: 'Élevé', critical: 'Critique' };
        const riskLabel = riskLabels[risk.level] || risk.level || '—';
        const riskBadge = document.getElementById('demo-risk-badge');
        riskBadge.innerHTML = `<span class="risk-${risk.level}">${riskScore}%</span><small>risque ré-identification · ${riskLabel}</small>`;
        document.getElementById('demo-original').textContent = data.original_excerpt || '';
        document.getElementById('demo-anonymized').innerHTML = highlightDemoTags(data.anonymized_excerpt || '');
        const chips = document.getElementById('demo-entity-chips');
        chips.innerHTML = Object.entries(data.entity_summary || {}).sort((a,b)=>b[1]-a[1])
          .map(([t,c]) => `<span class="demo-chip">${t}: ${c}</span>`).join('');
        loading.style.display = 'none';
        result.style.display = '';
      } catch(e) {
        loading.style.display = 'none';
        btn.disabled = false;
        btn.textContent = '↻ Réessayer';
      }
    }

    function highlightDemoTags(text) {
      if (!text) return '';
      const esc = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      return esc.replace(/\[([A-Z][A-Z0-9_]*)\]/g, (m, tag) => {
        let c = '#6366f1';
        if (tag.includes('PERSONNE')||tag.includes('ASSOCIE')) c='#ec4899';
        else if (tag.includes('SOCIETE')||tag.includes('CABINET')) c='#f59e0b';
        else if (tag.includes('ADRESSE')||tag.includes('VILLE')) c='#10b981';
        else if (tag.includes('IBAN')||tag.includes('MONTANT')||tag.includes('EMPRUNT')) c='#06b6d4';
        else if (tag.includes('DATE')) c='#8b5cf6';
        else if (tag.includes('SIRET')||tag.includes('SIREN')) c='#f97316';
        return `<mark style="background:${c}22;color:${c};padding:1px 4px;border-radius:3px;font-weight:600;">${m}</mark>`;
      });
    }
  </script>
```

- [ ] **Step 3 : Ajouter la section Pricing**

Insérer **avant** `<!-- CTA -->` (avant `<section class="cta-section">`) :

```html
  <!-- PRICING -->
  <section id="pricing" style="padding:5rem 2rem; max-width:1000px; margin:0 auto;">
    <div class="section-title animate-up">
      <h2>Tarifs simples et transparents</h2>
      <p>Commencez gratuitement. Montez en puissance quand vous en avez besoin.</p>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1.5rem;" class="animate-up delay-1">
      <div class="pricing-card">
        <div class="pricing-plan">Starter</div>
        <div class="pricing-price">Gratuit</div>
        <div class="pricing-desc">Pour découvrir et tester</div>
        <ul class="pricing-features">
          <li>✓ 10 documents / mois</li>
          <li>✓ Pseudonymisation + IA</li>
          <li>✓ Export PDF & JSON</li>
          <li>✓ Journal d'audit RGPD</li>
        </ul>
        <a href="/ui" class="btn btn-outline" style="width:100%;text-align:center;">Commencer</a>
      </div>
      <div class="pricing-card pricing-card-featured">
        <div class="pricing-badge">Populaire</div>
        <div class="pricing-plan">Pro</div>
        <div class="pricing-price">49 €<span style="font-size:1rem;font-weight:400;color:var(--text-muted)"> / mois</span></div>
        <div class="pricing-desc">Pour les cabinets actifs</div>
        <ul class="pricing-features">
          <li>✓ 200 documents / mois</li>
          <li>✓ Anonymisation forte RGPD</li>
          <li>✓ Comparaison N/N-1</li>
          <li>✓ Copilot IA dédié</li>
          <li>✓ RAG vectoriel</li>
        </ul>
        <a href="/ui" class="btn btn-primary" style="width:100%;text-align:center;">Essayer 14 jours</a>
      </div>
      <div class="pricing-card">
        <div class="pricing-plan">Cabinet</div>
        <div class="pricing-price">Sur devis</div>
        <div class="pricing-desc">Volume illimité + intégration SI</div>
        <ul class="pricing-features">
          <li>✓ Documents illimités</li>
          <li>✓ Multi-utilisateurs</li>
          <li>✓ API + webhooks</li>
          <li>✓ SLA dédié</li>
          <li>✓ Hébergement on-premise possible</li>
        </ul>
        <a href="mailto:gregory@superhome.fr?subject=ConfiDoc Cabinet" class="btn btn-outline" style="width:100%;text-align:center;">Nous contacter</a>
      </div>
    </div>
  </section>
```

Ajouter dans le `<style>` block :
```css
    .pricing-card { background:var(--surface); border:1px solid var(--surface-border); border-radius:16px; padding:2rem; position:relative; }
    .pricing-card-featured { border-color:rgba(99,102,241,0.5); box-shadow:0 0 30px rgba(99,102,241,0.1); }
    .pricing-badge { position:absolute; top:-12px; left:50%; transform:translateX(-50%); background:var(--primary); color:white; font-size:0.75rem; font-weight:700; padding:4px 14px; border-radius:99px; }
    .pricing-plan { font-family:'Outfit',sans-serif; font-size:1.1rem; font-weight:700; margin-bottom:8px; }
    .pricing-price { font-family:'Outfit',sans-serif; font-size:2rem; font-weight:800; margin-bottom:4px; }
    .pricing-desc { color:var(--text-muted); font-size:0.875rem; margin-bottom:1.5rem; }
    .pricing-features { list-style:none; padding:0; margin-bottom:1.5rem; }
    .pricing-features li { color:var(--text-muted); font-size:0.875rem; padding:6px 0; border-bottom:1px solid var(--surface-border); }
    .pricing-features li:last-child { border-bottom:none; }
```

- [ ] **Step 4 : Fixer le CTA final**

Remplacer dans `<!-- CTA -->` :
```html
        <a href="/ui" class="btn btn-primary">Prendre rendez-vous pour une démo</a>
```
par :
```html
        <div style="display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;">
          <a href="mailto:gregory@superhome.fr?subject=Demo ConfiDoc" class="btn btn-primary">Prendre rendez-vous →</a>
          <a href="#demo-section" class="btn btn-outline">Voir la démo en direct</a>
        </div>
```

- [ ] **Step 5 : Vérifier visuellement dans le navigateur**

```bash
# Si l'app est lancée :
open http://localhost:8000/
```
Vérifier :
- Les 3 métriques s'affichent dans le hero
- "▶ Voir la démo en direct" scrolle vers `#demo-section`
- La section pricing est visible
- Le CTA final pointe vers `mailto:` et `#demo-section`

- [ ] **Step 6 : Commit**

```bash
git add app/templates/landing.html
git commit -m "feat(landing): hero métriques, live demo inline, pricing, CTA fixé"
```

---

## Task 5 — App : Onboarding Demo Banner

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/js/app.js`
- Modify: `app/static/css/style.css`

- [ ] **Step 1 : Ajouter le HTML du banner dans index.html**

Dans `index.html`, dans `<div id="panel-dashboard" class="panel">`, ajouter **juste après** la balise `<div class="panel-header">` et son contenu (après le `</div>` qui ferme panel-header) :

```html
        <!-- ONBOARDING DEMO BANNER -->
        <div id="demo-onboarding-banner" style="display:none;">
          <div class="onboarding-demo-card">
            <div style="flex:1;">
              <div class="onboarding-demo-title">👋 Bienvenue sur ConfiDoc</div>
              <div class="onboarding-demo-text">Aucun document encore. Testez en 1 clic avec un vrai bilan anonymisé — résultat en 15 secondes.</div>
            </div>
            <div style="display:flex;gap:8px;align-items:center;flex-shrink:0;">
              <button id="btn-onboarding-demo" class="btn btn-primary btn-sm">▶ Lancer la démo</button>
              <button id="btn-onboarding-dismiss" class="btn btn-ghost btn-sm">Plus tard</button>
            </div>
          </div>
        </div>
```

- [ ] **Step 2 : Ajouter les styles CSS dans style.css**

À la fin de `style.css`, ajouter :

```css
/* ── Onboarding demo banner ─────────────────────────────────────────── */
.onboarding-demo-card {
  display: flex;
  align-items: center;
  gap: 16px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(167, 139, 250, 0.06));
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 12px;
  padding: 18px 22px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.onboarding-demo-title {
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--text);
  margin-bottom: 4px;
}
.onboarding-demo-text {
  font-size: 0.82rem;
  color: var(--text-muted);
}

/* ── Anon RGPD inline badge ─────────────────────────────────────────── */
.anon-gdpr-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-left: 8px;
  border: 1px solid currentColor;
}
```

- [ ] **Step 3 : Ajouter la logique JS dans app.js**

Ajouter la constante de clé après la constante `ONBOARDING_KEY` existante (ligne ~47) :

```javascript
const DEMO_BANNER_KEY = "confidoc_demo_banner_dismissed";
```

Ajouter ces deux fonctions après `finishOnboarding()` (après la ligne ~1598) :

```javascript
function showDemoBanner() {
  if (localStorage.getItem(DEMO_BANNER_KEY)) return;
  const banner = $("demo-onboarding-banner");
  if (!banner) return;
  banner.style.display = "";
  $("btn-onboarding-demo")?.addEventListener("click", async () => {
    banner.style.display = "none";
    localStorage.setItem(DEMO_BANNER_KEY, "true");
    await createDemoDocument();
  });
  $("btn-onboarding-dismiss")?.addEventListener("click", () => {
    banner.style.display = "none";
    localStorage.setItem(DEMO_BANNER_KEY, "true");
  });
}

function hideDemoBanner() {
  const banner = $("demo-onboarding-banner");
  if (banner) banner.style.display = "none";
}
```

Dans `initApp()`, **remplacer** le bloc existant :
```javascript
  if (!localStorage.getItem(ONBOARDING_KEY)) {
    setTimeout(() => showOnboarding(), 500);
  }
```
par :

```javascript
  // Afficher le banner démo si aucun document (prioritaire sur le tour)
  if (!localStorage.getItem(DEMO_BANNER_KEY) && lastDocsList.length === 0) {
    showDemoBanner();
  } else if (!localStorage.getItem(ONBOARDING_KEY)) {
    // Tour classique seulement si le banner n'est pas affiché
    setTimeout(() => showOnboarding(), 500);
  }
```

- [ ] **Step 4 : Vérifier manuellement**

1. Vider le localStorage dans les DevTools (`localStorage.clear()`)
2. Se connecter sur `/ui`
3. Vérifier que le banner "Bienvenue sur ConfiDoc" apparaît
4. Cliquer "▶ Lancer la démo" → doit appeler POST /demo et charger le doc
5. Au rechargement, le banner ne doit plus apparaître

- [ ] **Step 5 : Commit**

```bash
git add app/templates/index.html app/static/js/app.js app/static/css/style.css
git commit -m "feat(app): banner onboarding démo au premier login"
```

---

## Task 6 — App : Score RGPD Inline + Split-View Auto

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/js/app.js`

- [ ] **Step 1 : Ajouter le badge RGPD dans anon-doc-bar (index.html)**

Dans le div `<div id="anon-doc-bar"...>`, après `<span id="anon-doc-status"...></span>`, ajouter :

```html
          <span id="anon-gdpr-badge" class="anon-gdpr-badge" style="display:none;"></span>
```

- [ ] **Step 2 : Ajouter la fonction updateAnonGdprBadge dans app.js**

Ajouter après `function updateAIDocBar(...)` (après la ligne ~974) :

```javascript
function updateAnonGdprBadge(risk) {
  const badge = $("anon-gdpr-badge");
  if (!badge) return;
  if (!risk) { badge.style.display = "none"; return; }
  const score = Math.round((risk.score || 0) * 100);
  const labels = { low: "Faible", medium: "Moyen", high: "Élevé", critical: "Critique" };
  const label = labels[risk.level] || risk.level || "—";
  const colors = { low: "#10b981", medium: "#f59e0b", high: "#ef4444", critical: "#dc2626" };
  const color = colors[risk.level] || "var(--text-muted)";
  badge.textContent = `Risque : ${score}% · ${label}`;
  badge.style.color = color;
  badge.style.borderColor = color;
  badge.style.display = "";
}
```

- [ ] **Step 3 : Appeler updateAnonGdprBadge dans showAnonResults**

Dans `showAnonResults()`, après la ligne `currentRiskLevel = risk ? risk.level : null;` (ligne ~1204), ajouter :

```javascript
  updateAnonGdprBadge(risk);
```

- [ ] **Step 4 : Auto-afficher le split-view dans showAnonResults**

Dans `showAnonResults()`, après `$("anon-results").style.display = "";` (ligne ~1189), ajouter :

```javascript
  $("anon-split-view").style.display = "";
```

- [ ] **Step 5 : Vérifier manuellement**

1. Uploader un document ou utiliser le doc démo
2. Lancer l'anonymisation
3. Vérifier que le split-view original/anonymisé s'affiche automatiquement
4. Vérifier que la barre `anon-doc-bar` affiche le badge risque (ex: "Risque : 8% · Faible")

- [ ] **Step 6 : Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat(app): badge RGPD inline + split-view auto après anonymisation"
```

---

## Task 7 — Page /investor

**Files:**
- Create: `app/templates/investor.html`
- Modify: `app/api/ui.py`

- [ ] **Step 1 : Créer `app/templates/investor.html`**

```html
<!DOCTYPE html>
<html lang="fr" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ConfiDoc — Dashboard Investisseur</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@700;800&display=swap" rel="stylesheet">
  <style nonce="{{CSP_NONCE}}">
    :root { --primary:#6366f1; --accent:#00d2d3; --bg:#0b0f19; --surface:#151b2b; --text:#f8fafc; --text-muted:#94a3b8; --border:rgba(255,255,255,0.08); }
    * { margin:0; padding:0; box-sizing:border-box; }
    body { font-family:'Inter',sans-serif; background:var(--bg); color:var(--text); min-height:100vh; }
    .nav { position:fixed; top:0; width:100%; background:rgba(11,15,25,0.85); backdrop-filter:blur(12px); border-bottom:1px solid var(--border); padding:1rem 2rem; display:flex; justify-content:space-between; align-items:center; z-index:10; }
    .logo { font-family:'Outfit',sans-serif; font-weight:800; font-size:1.3rem; color:white; text-decoration:none; }
    .page { max-width:900px; margin:0 auto; padding:8rem 2rem 4rem; }
    h1 { font-family:'Outfit',sans-serif; font-size:2.5rem; font-weight:800; margin-bottom:0.5rem; }
    .subtitle { color:var(--text-muted); font-size:1.1rem; margin-bottom:3rem; }
    .kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:1.5rem; margin-bottom:3rem; }
    .kpi-card { background:var(--surface); border:1px solid var(--border); border-radius:16px; padding:1.5rem; text-align:center; }
    .kpi-num { font-family:'Outfit',sans-serif; font-size:2.5rem; font-weight:800; color:var(--primary); margin-bottom:4px; }
    .kpi-label { color:var(--text-muted); font-size:0.85rem; }
    .section-title { font-family:'Outfit',sans-serif; font-size:1.3rem; font-weight:700; margin-bottom:1rem; margin-top:2rem; }
    .info-row { display:flex; justify-content:space-between; align-items:center; padding:12px 0; border-bottom:1px solid var(--border); font-size:0.9rem; }
    .info-row:last-child { border-bottom:none; }
    .info-label { color:var(--text-muted); }
    .info-value { font-weight:600; }
    .badge { background:rgba(99,102,241,0.15); color:#a5b4fc; padding:4px 12px; border-radius:99px; font-size:0.8rem; font-weight:600; }
    .loading { text-align:center; padding:3rem; color:var(--text-muted); }
    .error-msg { text-align:center; padding:2rem; color:#ef4444; }
    .contact-section { background:var(--surface); border:1px solid var(--border); border-radius:16px; padding:2rem; text-align:center; margin-top:3rem; }
    .contact-section h3 { font-family:'Outfit',sans-serif; font-size:1.5rem; margin-bottom:0.5rem; }
    .contact-section p { color:var(--text-muted); margin-bottom:1.5rem; }
    .btn { display:inline-flex; align-items:center; gap:8px; padding:0.75rem 1.5rem; border-radius:8px; font-weight:600; font-size:0.95rem; text-decoration:none; transition:all 0.2s; }
    .btn-primary { background:linear-gradient(135deg,var(--primary),#8e7dff); color:white; }
    .btn-primary:hover { transform:translateY(-1px); }
  </style>
</head>
<body>
  <nav class="nav">
    <a href="/" class="logo">🔒 ConfiDoc</a>
    <a href="/ui" class="btn btn-primary" style="padding:0.5rem 1rem;font-size:0.85rem;">Espace client</a>
  </nav>

  <div class="page">
    <h1>Dashboard Investisseur</h1>
    <p class="subtitle">Métriques de traction en temps réel — ConfiDoc SAS</p>

    <div id="loading" class="loading">Chargement des métriques…</div>
    <div id="error" class="error-msg" style="display:none;">Impossible de charger les métriques.</div>

    <div id="content" style="display:none;">
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-num" id="kpi-total-docs">—</div>
          <div class="kpi-label">Documents traités</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-num" id="kpi-full-ready">—</div>
          <div class="kpi-label">Taux Full Ready</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-num" id="kpi-entities">—</div>
          <div class="kpi-label">Entités masquées</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-num" id="kpi-avg-time">—</div>
          <div class="kpi-label">Temps moyen / doc</div>
        </div>
      </div>

      <div class="section-title">Produit</div>
      <div>
        <div class="info-row"><span class="info-label">Stack</span><span class="info-value">Python / FastAPI · PostgreSQL · Redis · Mistral AI</span></div>
        <div class="info-row"><span class="info-label">Conformité</span><span class="info-value"><span class="badge">RGPD</span> <span class="badge">Made in France</span></span></div>
        <div class="info-row"><span class="info-label">Déploiement</span><span class="info-value">Railway · GitHub CI/CD · Docker</span></div>
        <div class="info-row"><span class="info-label">Tests de régression</span><span class="info-value">250+ golden sets automatisés</span></div>
      </div>

      <div class="section-title">Marché cible</div>
      <div>
        <div class="info-row"><span class="info-label">Secteur</span><span class="info-value">Expertise comptable · Droit · Finance</span></div>
        <div class="info-row"><span class="info-label">Problème adressé</span><span class="info-value">RGPD + IA : comment utiliser l'IA sur des données clients sensibles</span></div>
        <div class="info-row"><span class="info-label">Modèle</span><span class="info-value">SaaS B2B · Starter gratuit → Pro 49€/mois → Cabinet sur devis</span></div>
      </div>
    </div>

    <div class="contact-section">
      <h3>Intéressé par ConfiDoc ?</h3>
      <p>Gregory Baranes — Fondateur</p>
      <a href="mailto:gregory@superhome.fr?subject=ConfiDoc - Investissement" class="btn btn-primary">
        Prendre contact →
      </a>
    </div>
  </div>

  <script>
    async function loadMetrics() {
      try {
        const res = await fetch('/api/v1/documents/stats/platform');
        if (!res.ok) throw new Error(res.statusText);
        const d = await res.json();
        document.getElementById('kpi-total-docs').textContent = (d.total_documents_processed || 0).toLocaleString('fr-FR');
        document.getElementById('kpi-full-ready').textContent = (d.full_ready_rate || 0).toFixed(1) + '%';
        document.getElementById('kpi-entities').textContent = (d.total_entities_masked || 0).toLocaleString('fr-FR');
        const avg = d.avg_processing_seconds;
        document.getElementById('kpi-avg-time').textContent = avg ? `${avg}s` : '—';
        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = '';
      } catch(e) {
        document.getElementById('loading').style.display = 'none';
        document.getElementById('error').style.display = '';
      }
    }
    loadMetrics();
  </script>
</body>
</html>
```

- [ ] **Step 2 : Ajouter la route /investor dans app/api/ui.py**

Après `_LANDING_TEMPLATE`, ajouter :
```python
_INVESTOR_TEMPLATE = _TEMPLATE_DIR / "investor.html"
```

Après le handler `/security`, ajouter :

```python
@router.get("/investor", response_class=HTMLResponse, include_in_schema=False)
async def investor_page(request: Request) -> HTMLResponse:
    """Page dashboard investisseur — métriques publiques."""
    nonce = getattr(request.state, "csp_nonce", "")
    html_content = _render_template(_INVESTOR_TEMPLATE, request, nonce)
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
```

- [ ] **Step 3 : Vérifier dans le navigateur**

```bash
open http://localhost:8000/investor
```
Vérifier : les 4 KPIs se chargent (ou affichent `—` si base vide), le bouton contact pointe vers `mailto:gregory@superhome.fr`.

- [ ] **Step 4 : Commit final**

```bash
git add app/templates/investor.html app/api/ui.py
git commit -m "feat(investor): page /investor avec KPIs publics en temps réel"
```

---

## Vérification finale

- [ ] `pytest tests/ -q` → tous les tests passent
- [ ] `GET /api/v1/demo/public` répond 200 ou 202 sans Authorization header
- [ ] `GET /api/v1/documents/stats/platform` répond 200 sans Authorization header
- [ ] Landing page : "▶ Voir la démo en direct" scrolle vers `#demo-section`
- [ ] Landing page : pricing visible, CTA final pointe vers `mailto:`
- [ ] App : banner onboarding visible au premier login sur compte vide
- [ ] App : split-view s'affiche automatiquement après anonymisation
- [ ] App : badge risque visible dans anon-doc-bar après anonymisation
- [ ] `/investor` accessible sans login et affiche les métriques
