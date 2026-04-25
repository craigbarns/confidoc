# ConfiDoc — Redesign Dark Premium Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refonte visuelle complète Dark Premium (landing + auth + app) — zéro emoji, SVG icons, tokens unifiés, cohérence totale — + vérification Railway.

**Architecture:** Modifications CSS/HTML uniquement dans 3 fichiers (`style.css`, `index.html`, `landing.html`) + corrections icônes dynamiques dans `app.js`. Aucun changement backend.

**Tech Stack:** Vanilla HTML/CSS/JS, Inter (Google Fonts), SVG inline (style Lucide), FastAPI/Jinja2 templates, Railway hosting.

---

## SVG Icon Reference

Copier-coller ces blocs SVG dans les tâches ci-dessous. Remplacer `W` et `H` par la taille souhaitée.

```
SHIELD   : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>

EYE      : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>

EYE-OFF  : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>

FILE     : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>

GRID     : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>

CHECK    : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>

TRASH    : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>

UPLOAD   : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>

DOWNLOAD : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>

CLIPBOARD: <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>

PLAY     : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>

STOP     : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>

MENU     : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>

ALERT    : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>

MESSAGE  : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>

BARCHART : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>

FILETEXT : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg>

ARROW-R  : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>

BOT      : <svg width="W" height="H" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/><circle cx="12" cy="16" r="1"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>
```

---

## Task 1 — CSS Design Tokens

**Files:**
- Modify: `app/static/css/style.css:1-22`

- [ ] **Step 1: Update `:root` tokens**

In `style.css`, replace the entire `:root { ... }` block (lines 1–22) with:

```css
:root {
  --bg: #080810;
  --bg-card: rgba(13, 13, 24, 0.92);
  --bg-sidebar: rgba(10, 10, 20, 0.97);
  --glass: blur(16px) saturate(160%);
  --bg-hover: rgba(124, 116, 255, 0.08);
  --border: rgba(255, 255, 255, 0.07);
  --border-light: rgba(255, 255, 255, 0.11);
  --text: #f0f0ff;
  --text-muted: #8892b0;
  --text-dim: #4b5563;
  --accent: #7c74ff;
  --accent-hover: #9189ff;
  --accent-light: #a78bfa;
  --accent-dim: rgba(124, 116, 255, 0.12);
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --radius: 10px;
  --radius-lg: 14px;
  --radius-xl: 20px;
  --shadow-lg: 0 16px 48px -12px rgba(0,0,0,0.6);
  --shadow-sm: 0 4px 12px rgba(0,0,0,0.3);
}
```

- [ ] **Step 2: Verify visually**

Open `http://localhost:8000/ui` in the browser. The background should be noticeably darker (`#080810` vs `#0f1117`). Cards should feel deeper. No broken layouts.

- [ ] **Step 3: Commit**

```bash
git add app/static/css/style.css
git commit -m "style: update dark premium CSS tokens"
```

---

## Task 2 — Landing Page Refonte

**Files:**
- Modify: `app/templates/landing.html` (full rewrite of inline `<style>` + HTML)

- [ ] **Step 1: Replace the entire `landing.html` content**

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ConfiDoc — Confidentialité documentaire automatisée</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style nonce="{{CSP_NONCE}}">
    :root {
      --bg: #080810; --surface: #0d0d18; --border: rgba(255,255,255,0.07);
      --accent: #7c74ff; --accent-light: #a78bfa;
      --text: #f0f0ff; --muted: #8892b0; --dim: #4b5563;
    }
    * { margin:0; padding:0; box-sizing:border-box; }
    body { font-family:'Inter',system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }

    /* NAV */
    .nav { display:flex; justify-content:space-between; align-items:center; padding:20px 48px; max-width:1200px; margin:0 auto; border-bottom:1px solid var(--border); }
    .logo { display:flex; align-items:center; gap:10px; text-decoration:none; }
    .logo-icon { width:32px; height:32px; background:linear-gradient(135deg,var(--accent),var(--accent-light)); border-radius:8px; display:flex; align-items:center; justify-content:center; color:#fff; box-shadow:0 4px 16px -4px rgba(124,116,255,0.5); flex-shrink:0; }
    .logo-text { font-size:17px; font-weight:800; letter-spacing:-0.4px; color:var(--text); }
    .nav-links { display:flex; align-items:center; gap:32px; }
    .nav-links a { color:var(--muted); font-size:14px; font-weight:500; text-decoration:none; transition:color .2s; }
    .nav-links a:hover { color:var(--text); }
    .btn-nav { background:rgba(124,116,255,0.12); color:#9189ff; border:1px solid rgba(124,116,255,0.3); padding:8px 20px; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer; text-decoration:none; transition:all .2s; }
    .btn-nav:hover { background:rgba(124,116,255,0.22); }

    /* HERO */
    .hero { text-align:center; padding:80px 24px 60px; max-width:860px; margin:0 auto; position:relative; }
    .hero::before { content:''; position:absolute; top:-40px; left:50%; transform:translateX(-50%); width:600px; height:300px; background:radial-gradient(ellipse,rgba(124,116,255,0.12) 0%,transparent 70%); pointer-events:none; }
    .badge { display:inline-flex; align-items:center; gap:8px; border:1px solid rgba(124,116,255,0.3); color:#9189ff; padding:5px 14px; border-radius:999px; font-size:12px; font-weight:600; margin-bottom:24px; background:rgba(124,116,255,0.06); }
    .badge-dot { width:6px; height:6px; background:var(--accent); border-radius:50%; box-shadow:0 0 6px var(--accent); animation:pulse 2s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    .hero h1 { font-size:clamp(2.8rem,5vw,4.2rem); font-weight:900; line-height:1.05; letter-spacing:-2px; color:var(--text); margin-bottom:20px; }
    .hero h1 span { background:linear-gradient(135deg,var(--accent) 0%,var(--accent-light) 50%,#c4b5fd 100%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
    .hero p { font-size:1.1rem; color:var(--muted); max-width:560px; margin:0 auto 36px; line-height:1.7; }
    .hero-actions { display:flex; gap:12px; justify-content:center; flex-wrap:wrap; }
    .btn-primary { background:linear-gradient(135deg,var(--accent),#6c5ce7); color:#fff; padding:13px 28px; border-radius:10px; font-size:15px; font-weight:700; border:none; cursor:pointer; box-shadow:0 12px 32px -8px rgba(124,116,255,0.55); transition:all .2s; display:inline-flex; align-items:center; gap:8px; text-decoration:none; }
    .btn-primary:hover { transform:translateY(-2px); box-shadow:0 16px 40px -8px rgba(124,116,255,0.6); }
    .btn-ghost { background:rgba(255,255,255,0.05); color:#c9d1d9; padding:13px 24px; border-radius:10px; font-size:15px; font-weight:500; border:1px solid rgba(255,255,255,0.1); cursor:pointer; text-decoration:none; transition:all .2s; display:inline-flex; align-items:center; }
    .btn-ghost:hover { background:rgba(255,255,255,0.08); color:#fff; }

    /* STATS */
    .stats { display:grid; grid-template-columns:repeat(4,1fr); max-width:900px; margin:48px auto; padding:0 24px; gap:16px; }
    .stat { background:rgba(13,13,24,0.9); border:1px solid var(--border); border-radius:14px; padding:24px 20px; text-align:center; transition:border-color .2s; }
    .stat:hover { border-color:rgba(124,116,255,0.3); }
    .stat h3 { font-size:2rem; font-weight:900; color:var(--accent); letter-spacing:-1px; margin-bottom:4px; }
    .stat p { color:var(--muted); font-size:13px; }

    /* FEATURES */
    .features { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; max-width:1100px; margin:0 auto 80px; padding:0 24px; }
    .feature { background:rgba(10,10,20,0.9); border:1px solid var(--border); border-radius:14px; padding:28px 24px; transition:border-color .2s, transform .2s; }
    .feature:hover { border-color:rgba(124,116,255,0.25); transform:translateY(-2px); }
    .feature-icon { width:40px; height:40px; background:rgba(124,116,255,0.12); border-radius:10px; display:flex; align-items:center; justify-content:center; margin-bottom:16px; color:var(--accent); }
    .feature h4 { font-size:15px; font-weight:700; color:var(--text); margin-bottom:8px; }
    .feature p { color:var(--muted); font-size:13px; line-height:1.65; }

    /* CTA SECTION */
    .cta { text-align:center; padding:80px 24px; max-width:700px; margin:0 auto; }
    .cta h2 { font-size:2.5rem; font-weight:900; letter-spacing:-1.5px; margin-bottom:16px; color:var(--text); }
    .cta p { color:var(--muted); margin-bottom:32px; font-size:1rem; }

    footer { text-align:center; padding:32px 24px; color:var(--dim); font-size:13px; border-top:1px solid var(--border); }
  </style>
</head>
<body>
  <nav class="nav">
    <a href="/" class="logo">
      <span class="logo-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      </span>
      <span class="logo-text">ConfiDoc</span>
    </a>
    <div class="nav-links">
      <a href="#features">Fonctionnalités</a>
      <a href="#demo">Démo</a>
      <a href="/ui" class="btn-nav">Accéder à l'app →</a>
    </div>
  </nav>

  <section class="hero">
    <div class="badge">
      <span class="badge-dot"></span>
      Conformité RGPD native · Propulsé par IA
    </div>
    <h1>Anonymisez vos documents<br><span>sensibles en 10 secondes</span></h1>
    <p>ConfiDoc détecte et masque automatiquement les données personnelles et financières dans vos documents juridiques et comptables.</p>
    <div class="hero-actions">
      <a href="/ui" class="btn-primary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        Lancer la démo
      </a>
      <a href="mailto:contact@confidoc.fr" class="btn-ghost">Contacter l'équipe →</a>
    </div>
  </section>

  <section class="stats">
    <div class="stat"><h3>10s</h3><p>Anonymisation moyenne</p></div>
    <div class="stat"><h3>95%+</h3><p>Précision de détection</p></div>
    <div class="stat"><h3>RGPD</h3><p>Conformité native</p></div>
    <div class="stat"><h3>24/7</h3><p>Traitement automatisé</p></div>
  </section>

  <section class="features" id="features">
    <div class="feature">
      <div class="feature-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
      <h4>Anonymisation IA</h4>
      <p>Détection automatique des PII, données financières et juridiques avec remplacement intelligent par tokens.</p>
    </div>
    <div class="feature">
      <div class="feature-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></div>
      <h4>Score de risque RGPD</h4>
      <p>Évaluez le risque de réidentification de chaque document et recevez des recommandations d'actions.</p>
    </div>
    <div class="feature">
      <div class="feature-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></div>
      <h4>Agent Compliance IA</h4>
      <p>Discutez avec un agent IA spécialisé qui analyse vos documents anonymisés et répond à vos questions.</p>
    </div>
    <div class="feature">
      <div class="feature-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/></svg></div>
      <h4>Rapport d'audit PDF</h4>
      <p>Générez un rapport PDF complet traçant chaque modification pour vos dossiers de conformité.</p>
    </div>
    <div class="feature">
      <div class="feature-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg></div>
      <h4>Pipeline asynchrone</h4>
      <p>Upload et déposez-vous : notre infrastructure traite vos documents en arrière-plan sans interruption.</p>
    </div>
    <div class="feature">
      <div class="feature-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></div>
      <h4>Sécurité enterprise</h4>
      <p>Chiffrement AES-256, JWT, headers de sécurité et isolation des données par organisation.</p>
    </div>
  </section>

  <section class="cta" id="demo">
    <h2>Prêt à protéger<br>vos documents ?</h2>
    <p>Testez ConfiDoc avec un document de démonstration. Aucune inscription requise.</p>
    <a href="/ui" class="btn-primary" style="display:inline-flex;margin:0 auto">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      Lancer la démo interactive
    </a>
  </section>

  <footer>© 2025 ConfiDoc — Confidentialité documentaire automatisée pour professions réglementées.</footer>
</body>
</html>
```

- [ ] **Step 2: Vérifier visuellement**

Ouvrir `http://localhost:8000/` dans le navigateur. Vérifier :
- Logo SVG shield violet en haut à gauche
- Hero avec gradient violet sur le texte clé
- Icônes SVG dans les features cards (pas d'emoji)
- Badge avec dot animé

- [ ] **Step 3: Commit**

```bash
git add app/templates/landing.html
git commit -m "style: refonte landing page dark premium — SVG icons, violet brand"
```

---

## Task 3 — Inter Font + SVG Logo dans l'app

**Files:**
- Modify: `app/templates/index.html:1-35` (head + header logo)
- Modify: `app/static/css/style.css:79-88` (logo CSS)

- [ ] **Step 1: Ajouter Inter dans le `<head>` de `index.html`**

Après `<link rel="stylesheet" href="/static/css/style.css" />` (ligne 7), ajouter :

```html
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Mettre à jour le favicon SVG dans `<head>`**

Remplacer la ligne du favicon (ligne 10) :
```html
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔒</text></svg>" type="image/svg+xml" />
```
Par :
```html
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%237c74ff'/><path d='M50 15 L75 25 L75 50 C75 68 50 85 50 85 C50 85 25 68 25 50 L25 25 Z' fill='white' stroke='white'/></svg>" type="image/svg+xml" />
```

- [ ] **Step 3: Remplacer le logo emoji dans le header**

Dans `index.html`, remplacer (ligne 19) :
```html
      <span class="logo-icon" role="img" aria-label="Cadenas">🔒</span>
```
Par :
```html
      <span class="logo-icon" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></span>
```

- [ ] **Step 4: Mettre à jour le CSS du logo dans `style.css`**

Remplacer les lignes 79–88 :
```css
.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.3px;
}
.logo-icon { font-size: 18px; }
.logo-text { font-size: 16px; font-weight: 700; letter-spacing: -0.3px; }
```
Par :
```css
.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'Inter', system-ui, sans-serif;
  font-weight: 700;
  letter-spacing: -0.3px;
  text-decoration: none;
}
.logo-icon {
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg, #7c74ff, #a78bfa);
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.logo-text { font-size: 15px; font-weight: 800; letter-spacing: -0.3px; }
```

- [ ] **Step 5: Ajouter Inter à la font-family globale dans `style.css`**

Remplacer dans `body` (ligne ~51) :
```css
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```
Par :
```css
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

- [ ] **Step 6: Vérifier**

Ouvrir `/ui`. Le logo doit montrer un carré violet avec icône shield blanche à gauche du texte "ConfiDoc". La police Inter doit être visible (lettres plus propres).

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html app/static/css/style.css
git commit -m "style: Inter font, SVG logo box dans l'app"
```

---

## Task 4 — Auth Screen — Icons + CSS Polish

**Files:**
- Modify: `app/templates/index.html:37-91` (auth section)
- Modify: `app/static/css/style.css:120-163` (auth CSS)

- [ ] **Step 1: Remplacer l'icône auth logo dans `index.html`**

Remplacer (ligne 39–41) :
```html
    <div class="auth-logo">
      <span class="auth-logo-icon" role="img" aria-label="Cadenas">🔒</span>
    </div>
```
Par :
```html
    <div class="auth-logo">
      <span class="auth-logo-icon" aria-hidden="true">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      </span>
    </div>
```

- [ ] **Step 2: Remplacer l'icône eye (show password) dans `index.html`**

Remplacer (ligne 52–53) :
```html
          <button type="button" id="btn-toggle-password" class="btn-password-toggle" aria-label="Afficher le mot de passe" aria-pressed="false" title="Afficher">👁️<span class="sr-only">Afficher</span></button>
```
Par :
```html
          <button type="button" id="btn-toggle-password" class="btn-password-toggle" aria-label="Afficher le mot de passe" aria-pressed="false" title="Afficher"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg><span class="sr-only">Afficher</span></button>
```

- [ ] **Step 3: Remplacer l'icône eye du reset password dans `index.html`**

Remplacer (ligne 72) :
```html
          <button type="button" id="btn-toggle-reset-password" class="btn-password-toggle" title="Afficher">👁</button>
```
Par :
```html
          <button type="button" id="btn-toggle-reset-password" class="btn-password-toggle" title="Afficher"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></button>
```

- [ ] **Step 4: Polish auth card CSS dans `style.css`**

Remplacer les lignes 121–163 :
```css
#screen-auth {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}
.auth-card {
  background: var(--bg-card);
  backdrop-filter: var(--glass);
  -webkit-backdrop-filter: var(--glass);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 48px 40px;
  width: 420px;
  box-shadow: var(--shadow-lg);
  transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
.auth-card:hover { box-shadow: var(--shadow-lg), 0 0 0 1px var(--border-light); }
.auth-logo {
  text-align: center;
  font-size: 40px;
  margin-bottom: 16px;
}
.auth-logo-icon { font-size: 40px; }
```
Par :
```css
#screen-auth {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  background-image: radial-gradient(ellipse at 50% 0%, rgba(124,116,255,0.1) 0%, transparent 60%);
}
.auth-card {
  background: var(--bg-card);
  backdrop-filter: var(--glass);
  -webkit-backdrop-filter: var(--glass);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  padding: 40px 36px;
  width: 420px;
  box-shadow: 0 24px 80px -16px rgba(0,0,0,0.6), 0 0 0 1px rgba(124,116,255,0.05);
}
.auth-logo {
  text-align: center;
  margin-bottom: 20px;
}
.auth-logo-icon {
  display: inline-flex;
  width: 52px;
  height: 52px;
  background: linear-gradient(135deg, var(--accent), var(--accent-light));
  border-radius: 14px;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 8px 24px -6px rgba(124,116,255,0.5);
}
```

- [ ] **Step 5: Polir le bouton submit auth dans `style.css`**

Trouver `.btn.btn-primary.btn-full` ou le sélecteur de `.btn-primary` utilisé dans auth. Vérifier que le bouton de login a un `box-shadow` teinté. Chercher dans style.css :

```bash
grep -n "btn-primary" app/static/css/style.css | head -10
```

Si `.btn-primary` n'a pas de `box-shadow`, ajouter après la règle existante :
```css
.btn.btn-primary { box-shadow: 0 8px 20px -6px rgba(124,116,255,0.35); }
.btn.btn-primary:hover { box-shadow: 0 12px 28px -6px rgba(124,116,255,0.5); transform: translateY(-1px); }
```

- [ ] **Step 6: Vérifier**

Ouvrir `/ui`. L'écran de login doit afficher :
- Fond avec halo violet en haut
- Carte centrée avec corners arrondis (20px)
- Icône shield dans carré gradient violet
- Bouton eye SVG visible dans le champ password

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html app/static/css/style.css
git commit -m "style: auth screen — SVG icons, gradient logo, polish card"
```

---

## Task 5 — Header Action Buttons

**Files:**
- Modify: `app/templates/index.html:23-31` (header actions)
- Modify: `app/static/css/style.css:94-115` (header-actions CSS)

- [ ] **Step 1: Remplacer les boutons header dans `index.html`**

Remplacer les lignes 23–31 :
```html
    <div class="header-actions">
      <button id="btn-sidebar-toggle" class="sidebar-toggle" aria-label="Menu documents">☰</button>
      <button id="btn-theme" class="btn-theme-toggle theme-switch" aria-label="Changer le thème" role="switch" aria-checked="false"></button>
      <span id="header-doc-pill" class="context-pill" style="display:none"></span>
      <span id="header-provider-pill" class="context-pill muted" style="display:none"></span>
      <a href="/security" target="_blank" class="btn btn-ghost btn-sm" id="btn-security" style="display:none" title="Securite &amp; Conformite RGPD" role="img" aria-label="Bouclier securite">🛡️</a>
      <button id="btn-dashboard" class="btn btn-ghost btn-sm" style="display:none" title="Dashboard" role="img" aria-label="Dashboard">📊</button>
      <span id="user-info" class="user-info"></span>
      <button id="btn-logout" class="btn btn-ghost btn-sm" style="display:none">Deconnexion</button>
    </div>
```
Par :
```html
    <div class="header-actions">
      <button id="btn-sidebar-toggle" class="sidebar-toggle" aria-label="Menu documents"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg></button>
      <button id="btn-theme" class="btn-theme-toggle theme-switch" aria-label="Changer le thème" role="switch" aria-checked="false"></button>
      <span id="header-doc-pill" class="context-pill" style="display:none"></span>
      <span id="header-provider-pill" class="context-pill muted" style="display:none"></span>
      <a href="/security" target="_blank" class="btn btn-ghost btn-sm btn-icon" id="btn-security" style="display:none" title="Sécurité &amp; Conformité RGPD" aria-label="Sécurité RGPD"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></a>
      <button id="btn-dashboard" class="btn btn-ghost btn-sm btn-icon" style="display:none" title="Dashboard" aria-label="Dashboard"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg></button>
      <span id="user-info" class="user-info"></span>
      <button id="btn-logout" class="btn btn-ghost btn-sm" style="display:none">Déconnexion</button>
    </div>
```

- [ ] **Step 2: Ajouter les styles des boutons icônes dans `style.css`**

Après `.header-actions { ... }` (ligne 94), ajouter :
```css
.btn-icon {
  width: 32px;
  height: 32px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn-icon:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-dim);
}
```

- [ ] **Step 3: Vérifier**

Après login dans l'app, les boutons dashboard et sécurité doivent afficher des icônes SVG (pas d'emoji). Le bouton menu sidebar doit avoir des lignes SVG.

- [ ] **Step 4: Commit**

```bash
git add app/templates/index.html app/static/css/style.css
git commit -m "style: header — icônes SVG, btn-icon class"
```

---

## Task 6 — Dashboard KPI Icons

**Files:**
- Modify: `app/templates/index.html:160-180` (dashboard KPI cards)
- Modify: `app/static/css/style.css` (dash-kpi-icon styles)

- [ ] **Step 1: Remplacer les icônes KPI dans `index.html`**

Remplacer les 4 `.dash-kpi-icon` (lignes 160–180) :
```html
            <div class="dash-kpi-card">
              <div class="dash-kpi-icon">📄</div>
              ...
            </div>
            <div class="dash-kpi-card">
              <div class="dash-kpi-icon">🔒</div>
              ...
            </div>
            <div class="dash-kpi-card">
              <div class="dash-kpi-icon">✅</div>
              ...
            </div>
            <div class="dash-kpi-card">
              <div class="dash-kpi-icon">🗑️</div>
              ...
            </div>
```
Par :
```html
            <div class="dash-kpi-card">
              <div class="dash-kpi-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>
              <div class="dash-kpi-num" id="dash-total-docs">0</div>
              <div class="dash-kpi-label">Documents</div>
            </div>
            <div class="dash-kpi-card kpi-success">
              <div class="dash-kpi-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
              <div class="dash-kpi-num" id="dash-total-entities">0</div>
              <div class="dash-kpi-label">Entités masquées</div>
            </div>
            <div class="dash-kpi-card kpi-success">
              <div class="dash-kpi-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg></div>
              <div class="dash-kpi-num" id="dash-ready-count">0</div>
              <div class="dash-kpi-label">Prêts IA</div>
            </div>
            <div class="dash-kpi-card kpi-muted">
              <div class="dash-kpi-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></div>
              <div class="dash-kpi-num" id="dash-trashed">0</div>
              <div class="dash-kpi-label">Corbeille</div>
            </div>
```

- [ ] **Step 2: Mettre à jour les styles des KPI cards dans `style.css`**

Trouver `.dash-kpi-icon` dans style.css et remplacer sa règle par :
```css
.dash-kpi-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: var(--accent-dim);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}
.dash-kpi-card.kpi-success .dash-kpi-icon { background: rgba(16,185,129,0.12); color: #10b981; }
.dash-kpi-card.kpi-muted .dash-kpi-icon { background: rgba(107,114,128,0.12); color: #6b7280; }
```

- [ ] **Step 3: Vérifier**

Dashboard : 4 KPI cards avec icônes SVG dans box colorée. Documents = violet, masquées = vert, prêts IA = vert, corbeille = gris.

- [ ] **Step 4: Commit**

```bash
git add app/templates/index.html app/static/css/style.css
git commit -m "style: dashboard KPI — SVG icons dans box colorée"
```

---

## Task 7 — Upload Panel

**Files:**
- Modify: `app/templates/index.html:271-293` (upload zone)
- Modify: `app/static/css/style.css:624-640` (upload-zone + upload-icon)

- [ ] **Step 1: Remplacer l'icône upload + bouton démo dans `index.html`**

Remplacer les lignes 271–282 :
```html
        <div style="margin: 12px 0; text-align: center">
          <button id="btn-demo" class="btn btn-primary" type="button" title="Démo instantanée pour les investisseurs">
            🚀 Essayer avec un document de démo
          </button>
        </div>
        <div class="upload-zone" id="upload-zone">
          <div class="upload-icon" role="img" aria-label="Document">📄</div>
          <p class="upload-main">Glissez votre fichier ici ou</p>
```
Par :
```html
        <div style="margin: 12px 0; text-align: center">
          <button id="btn-demo" class="btn btn-primary" type="button" title="Démo instantanée">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Essayer avec un document de démo
          </button>
        </div>
        <div class="upload-zone" id="upload-zone">
          <div class="upload-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg></div>
          <p class="upload-main">Glissez votre fichier ici ou</p>
```

- [ ] **Step 2: Mettre à jour les format badges dans `index.html`**

Remplacer les `.format-badge` (lignes ~288–292) :
```html
          <span class="format-badge">📄 PDF</span>
          <span class="format-badge">🖼 PNG</span>
          <span class="format-badge">🖼 JPG</span>
          <span class="format-badge">🖼 TIFF</span>
```
Par :
```html
          <span class="format-badge">PDF</span>
          <span class="format-badge">PNG</span>
          <span class="format-badge">JPG</span>
          <span class="format-badge">TIFF</span>
          <span class="format-badge">max 50 MB</span>
```

- [ ] **Step 3: Mettre à jour `.upload-icon` dans `style.css`**

Remplacer la ligne 637 :
```css
.upload-icon { font-size: 40px; margin-bottom: 14px; }
```
Par :
```css
.upload-icon {
  width: 52px;
  height: 52px;
  background: var(--accent-dim);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  color: var(--accent);
}
```

- [ ] **Step 4: Polir la `.upload-zone` dans `style.css`**

Remplacer les lignes 625–636 :
```css
.upload-zone {
  border: 2px dashed var(--border-light);
  border-radius: var(--radius-lg);
  padding: 48px 32px;
  text-align: center;
  transition: all 0.2s;
  max-width: 560px;
}
.upload-zone:hover, .upload-zone.drag-over {
  border-color: var(--accent);
  background: var(--accent-dim);
}
```
Par :
```css
.upload-zone {
  border: 2px dashed rgba(124,116,255,0.25);
  border-radius: var(--radius-lg);
  padding: 48px 32px;
  text-align: center;
  transition: all 0.2s;
  max-width: 560px;
  background: rgba(124,116,255,0.03);
  cursor: pointer;
}
.upload-zone:hover, .upload-zone.drag-over {
  border-color: rgba(124,116,255,0.55);
  background: rgba(124,116,255,0.08);
}
```

- [ ] **Step 5: Vérifier**

Panel upload : icône SVG cloud-upload dans box violette, bouton démo avec icône play, badges format sans emoji.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html app/static/css/style.css
git commit -m "style: upload panel — SVG icon, upload zone polish"
```

---

## Task 8 — Anon Panel + AI Panel Icons

**Files:**
- Modify: `app/templates/index.html:330-497` (panels anon et ai)

- [ ] **Step 1: Remplacer l'icône hint dans panel-anon (`index.html` ligne 332)**

Remplacer :
```html
        <div id="anon-empty" class="panel-empty-hint">
          <div class="hint-icon">👈</div>
```
Par :
```html
        <div id="anon-empty" class="panel-empty-hint">
          <div class="hint-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>
```

- [ ] **Step 2: Remplacer l'emoji ⚠️ dans le split view**

Remplacer (ligne 364) :
```html
                <h4>Original ⚠️</h4>
```
Par :
```html
                <h4>Original <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" style="vertical-align:-1px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></h4>
```

- [ ] **Step 3: Remplacer les boutons export avec emoji dans le panel AI**

Remplacer (lignes 401–404) :
```html
            <button id="btn-export-txt" class="btn btn-ghost btn-sm">⬇ Texte</button>
            <button id="btn-export-pdf" class="btn btn-ghost btn-sm">⬇ PDF redacté</button>
            <button id="btn-audit-report" class="btn btn-ghost btn-sm">📋 Audit RGPD</button>
            <button id="btn-compliance-report" class="btn btn-ghost btn-sm">📊 Conformite</button>
```
Par :
```html
            <button id="btn-export-txt" class="btn btn-ghost btn-sm"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Texte</button>
            <button id="btn-export-pdf" class="btn btn-ghost btn-sm"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> PDF</button>
            <button id="btn-audit-report" class="btn btn-ghost btn-sm"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/></svg> Audit RGPD</button>
            <button id="btn-compliance-report" class="btn btn-ghost btn-sm"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg> Conformité</button>
```

- [ ] **Step 4: Remplacer les quick-btn emojis dans le panel AI**

Remplacer (lignes 433–438) :
```html
          <button class="quick-btn" data-q="Fais un résumé de ce document.">📝 Résumé</button>
          <button class="quick-btn" data-q="Quels sont les points clés ?">🔑 Points clés</button>
          <button class="quick-btn" data-q="Y a-t-il des anomalies ou alertes ?">⚠️ Anomalies</button>
          <button class="quick-btn" data-q="Donne-moi les chiffres principaux.">📊 Chiffres</button>
          <button id="btn-copilot-mode" class="quick-btn" data-on="false">🤖 Copilot: OFF</button>
          <button id="btn-report-mode" class="quick-btn" data-on="false">🧱 Mode rapport: OFF</button>
```
Par :
```html
          <button class="quick-btn" data-q="Fais un résumé de ce document.">Résumé</button>
          <button class="quick-btn" data-q="Quels sont les points clés ?">Points clés</button>
          <button class="quick-btn" data-q="Y a-t-il des anomalies ou alertes ?">Anomalies</button>
          <button class="quick-btn" data-q="Donne-moi les chiffres principaux.">Chiffres</button>
          <button id="btn-copilot-mode" class="quick-btn" data-on="false">Copilot: OFF</button>
          <button id="btn-report-mode" class="quick-btn" data-on="false">Mode rapport: OFF</button>
```

- [ ] **Step 5: Remplacer les boutons actions review dans l'AI panel**

Remplacer (lignes 483–484) :
```html
            <button id="btn-review-copy" class="btn btn-ghost btn-sm">📋 Copier</button>
            <button id="btn-review-export" class="btn btn-ghost btn-sm">⬇ Exporter</button>
```
Par :
```html
            <button id="btn-review-copy" class="btn btn-ghost btn-sm"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg> Copier</button>
            <button id="btn-review-export" class="btn btn-ghost btn-sm"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Exporter</button>
```

- [ ] **Step 6: Remplacer les boutons copy/stop dans la zone chat**

Remplacer (lignes 492–493) :
```html
            <button id="btn-copy-answer" class="btn btn-ghost btn-sm" disabled>📋 Copier</button>
            <button id="btn-stop-stream" class="btn btn-ghost btn-sm" style="display:none">⏹ Stop</button>
```
Par :
```html
            <button id="btn-copy-answer" class="btn btn-ghost btn-sm" disabled><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg> Copier</button>
            <button id="btn-stop-stream" class="btn btn-ghost btn-sm" style="display:none"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg> Stop</button>
```

- [ ] **Step 7: Remplacer l'icône chat-intro dans index.html**

Remplacer (ligne 469) :
```html
            <div class="chat-intro-icon" role="img" aria-label="Cadenas">🔒</div>
```
Par :
```html
            <div class="chat-intro-icon"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
```

- [ ] **Step 8: Mettre à jour CSS chat-intro-icon et hint-icon dans `style.css`**

Remplacer la ligne 871 :
```css
.chat-intro-icon { font-size: 28px; margin-bottom: 10px; }
```
Par :
```css
.chat-intro-icon {
  width: 52px;
  height: 52px;
  background: var(--accent-dim);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
  color: var(--accent);
}
```

Remplacer la ligne 614–617 :
```css
.hint-icon {
  font-size: 32px;
  margin-bottom: 12px;
}
```
Par :
```css
.hint-icon {
  width: 52px;
  height: 52px;
  background: var(--accent-dim);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  color: var(--accent);
}
```

- [ ] **Step 9: Vérifier**

Panel Anon : icône file SVG dans l'état vide. Panel AI : boutons d'action avec SVG, quick-btns texte seul, chat intro avec icône shield dans box violette.

- [ ] **Step 10: Commit**

```bash
git add app/templates/index.html app/static/css/style.css
git commit -m "style: anon + AI panels — SVG icons, suppr emojis"
```

---

## Task 9 — app.js Dynamic Icons

**Files:**
- Modify: `app/static/js/app.js:437,442,965,1007,1496,2390,2395,2480`

- [ ] **Step 1: Fixer le context pill dans `app.js` (ligne 437)**

Remplacer :
```js
    docPill.textContent = `📄 ${currentDocName} · ${labelMap[currentDocStatus] || currentDocStatus || "—"}`;
```
Par :
```js
    docPill.textContent = `${currentDocName} · ${labelMap[currentDocStatus] || currentDocStatus || "—"}`;
```

- [ ] **Step 2: Fixer le provider pill (ligne 442)**

Remplacer :
```js
  providerPill.textContent = `🤖 Provider IA: ${currentProvider || "—"}`;
```
Par :
```js
  providerPill.textContent = `IA: ${currentProvider || "—"}`;
```

- [ ] **Step 3: Fixer le hint-icon à l'upload success (ligne 965)**

Remplacer :
```js
      $("anon-empty").querySelector(".hint-icon").textContent = "📄";
```
Par :
```js
      $("anon-empty").querySelector(".hint-icon").innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
```

- [ ] **Step 4: Trouver et fixer le hint-icon 🚀 (ligne ~1007)**

Chercher la ligne :
```js
$("anon-empty").querySelector(".hint-icon").textContent = "🚀";
```
Remplacer par :
```js
$("anon-empty").querySelector(".hint-icon").innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
```

- [ ] **Step 5: Fixer le reset du chat (ligne 1496)**

Remplacer :
```js
  $("chat-messages").innerHTML =
    '<div class="chat-intro"><div class="chat-intro-icon">🔒</div>' +
    "<p>Document anonymisé. Posez vos questions en toute sécurité.</p></div>";
```
Par :
```js
  $("chat-messages").innerHTML =
    '<div class="chat-intro"><div class="chat-intro-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>' +
    "<p>Document anonymisé. Posez vos questions en toute sécurité.</p></div>";
```

- [ ] **Step 6: Fixer le toggle password eye/eye-off (lignes ~2388–2398)**

Remplacer le bloc complet :
```js
      if (inp.type === "password") {
        inp.type = "text";
        btn.textContent = "🙈️";
        btn.title = "Masquer le mot de passe";
        btn.setAttribute("aria-pressed", "true");
      } else {
        inp.type = "password";
        btn.textContent = "👁️";
        btn.title = "Afficher le mot de passe";
        btn.setAttribute("aria-pressed", "false");
      }
```
Par :
```js
      const EYE_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
      const EYEOFF_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
      if (inp.type === "password") {
        inp.type = "text";
        btn.innerHTML = EYEOFF_SVG;
        btn.title = "Masquer le mot de passe";
        btn.setAttribute("aria-pressed", "true");
      } else {
        inp.type = "password";
        btn.innerHTML = EYE_SVG;
        btn.title = "Afficher le mot de passe";
        btn.setAttribute("aria-pressed", "false");
      }
```

Note: Il y a deux blocs toggle-password dans app.js (lignes ~2388 et ~2475). Appliquer le même remplacement aux deux.

- [ ] **Step 7: Vérifier**

1. Login → le context pill en haut affiche le nom du doc sans emoji
2. Upload d'un doc → le hint-icon affiche un SVG file
3. Chat reset → affiche l'icône shield SVG
4. Toggle password → affiche SVG eye/eye-off

- [ ] **Step 8: Commit**

```bash
git add app/static/js/app.js
git commit -m "style: app.js — remplacer emojis dynamiques par SVG"
```

---

## Task 10 — Railway Verification

**Files:** Aucun fichier modifié — vérification de l'état de production.

- [ ] **Step 1: Vérifier le health endpoint**

```bash
curl -s https://<your-railway-url>/api/v1/health | python3 -m json.tool
```
Résultat attendu :
```json
{"status": "ok"}
```
Si 404 : chercher la route dans `app/api/v1/router.py` ou `app/api/health.py`.

- [ ] **Step 2: Vérifier les static files**

```bash
curl -I https://<your-railway-url>/static/css/style.css
```
Attendu : `Content-Type: text/css`, HTTP 200.

```bash
curl -I https://<your-railway-url>/static/js/app.js
```
Attendu : `Content-Type: application/javascript`, HTTP 200.

- [ ] **Step 3: Vérifier la landing**

```bash
curl -s https://<your-railway-url>/ | grep -c "ConfiDoc"
```
Attendu : au moins `2`.

- [ ] **Step 4: Vérifier l'app**

```bash
curl -s https://<your-railway-url>/ui | grep -c "screen-auth"
```
Attendu : `1`.

- [ ] **Step 5: Vérifier l'auth (login)**

Dans un navigateur sur l'URL Railway :
1. Aller sur `/ui`
2. Se connecter avec un compte test
3. Vérifier : pas d'erreur console JS, dashboard charge, sidebar visible

- [ ] **Step 6: Vérifier l'upload**

1. Cliquer "Essayer avec un document de démo"
2. Vérifier que le statut passe de `uploadé` → `traitement` → `prêt IA`
3. Vérifier : pas d'erreur 500 dans la console Network

- [ ] **Step 7: Vérifier le rapport PDF**

1. Sélectionner un document `ready`
2. Aller dans le panel AI
3. Cliquer "Audit RGPD"
4. Vérifier : un PDF se télécharge sans erreur

- [ ] **Step 8: Vérifier les CSP headers**

Dans la console DevTools (F12) → Console. Vérifier l'absence de :
```
Refused to apply inline style because it violates the following Content Security Policy directive
```

Si des erreurs CSP apparaissent liées au style du nouveau `landing.html`, vérifier que le `nonce="{{CSP_NONCE}}"` est bien présent sur la balise `<style>`.

- [ ] **Step 9: Commit final**

```bash
git add .
git commit -m "style: redesign dark premium complet — landing, auth, app, icons SVG"
git push origin main
```

---

## Self-Review

**Spec coverage :**
- [x] Tokens CSS → Task 1
- [x] Typographie Inter → Task 3
- [x] SVG icons partout → Tasks 3–9
- [x] Landing page refonte → Task 2
- [x] Auth card polish → Task 4
- [x] Header icon buttons → Task 5
- [x] Dashboard KPI → Task 6
- [x] Upload panel → Task 7
- [x] Anon + AI panels → Task 8
- [x] app.js dynamic icons → Task 9
- [x] Railway checklist 10 points → Task 10
- [x] Zéro emoji règle → Tasks 3–9 couvrent tous les emojis listés dans la spec

**Aucun placeholder ni TBD.**

**Cohérence types :** `$("element-id")` est la convention existante dans app.js (helper function). Confirmé à la ligne 437. Utilisé de façon cohérente dans Task 9.
