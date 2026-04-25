# ConfiDoc — Redesign Dark Premium + Vérification Railway

**Date :** 2026-04-25  
**Direction validée :** A — Dark Premium (style Linear / Vercel)  
**Périmètre :** Landing page + Auth + App complète + vérification Railway

---

## 1. Système de design

### Tokens (remplacent les variables actuelles)

| Token | Valeur | Usage |
|---|---|---|
| `--bg` | `#080810` | Fond global (plus sombre qu'actuel `#0f1117`) |
| `--surface` | `#0d0d18` | Fond cards/modales |
| `--surface-2` | `#111120` | Fond sidebar, header |
| `--border` | `rgba(255,255,255,0.07)` | Bordures par défaut |
| `--border-accent` | `rgba(124,116,255,0.3)` | Bordures hover/focus |
| `--accent` | `#7c74ff` | Couleur primaire (violet) |
| `--accent-light` | `#a78bfa` | Gradient secondaire |
| `--accent-dim` | `rgba(124,116,255,0.12)` | Backgrounds accent doux |
| `--text` | `#f0f0ff` | Texte principal |
| `--text-muted` | `#8892b0` | Texte secondaire |
| `--text-dim` | `#4b5563` | Texte tertiaire |
| `--success` | `#10b981` | Vert (ready, OK) |
| `--warning` | `#f59e0b` | Orange (processing) |
| `--danger` | `#ef4444` | Rouge (failed) |
| `--radius` | `10px` | Radius standard |
| `--radius-lg` | `14px` | Radius cards |
| `--radius-xl` | `20px` | Radius modales |

### Typographie
- **Font :** Inter (déjà sur landing, à ajouter dans l'app via `<link>` Google Fonts)
- **Headings :** `font-weight: 800–900`, `letter-spacing: -1px` à `-2px`
- **Body :** `font-weight: 400–500`, `line-height: 1.6`
- **Labels :** `font-size: 11px`, `font-weight: 600`, `text-transform: uppercase`, `letter-spacing: 0.3px`

### Icônes
- **Règle absolue :** zéro emoji dans l'UI. Remplacé par SVG inline style Lucide.
- Icônes concernées : logo (shield), document (file), upload (cloud-upload), dashboard (grid), sécurité (shield), soleil/lune (theme toggle), utilisateur (user), déconnexion (log-out), corbeille (trash), statuts (check, clock, x-circle).
- Taille standard : 14–16px dans les boutons, 18–20px dans les feature cards, 26px dans l'auth logo.

---

## 2. Fichiers à modifier

| Fichier | Nature du changement |
|---|---|
| `app/templates/landing.html` | Refonte complète du CSS inline + contenu |
| `app/templates/index.html` | Mise à jour tokens + Inter font + SVG icons |
| `app/static/css/style.css` | Mise à jour tokens, composants, icônes |
| `app/static/js/app.js` | Aucun changement fonctionnel, seulement si des emojis sont injectés dynamiquement |

---

## 3. Landing page (`landing.html`)

**Changements :**
- Unifier couleur principale : `#0ea5e9` → `#7c74ff` (violet, cohérent avec app)
- Logo : icône SVG shield dans un carré arrondi gradient + texte "ConfiDoc"
- Hero badge : border + dot pulsant au lieu de fond plein
- H1 : gradient `#7c74ff → #a78bfa → #c4b5fd` sur le mot clé
- CTAs : bouton primaire gradient violet avec `box-shadow` teinté violet
- Stats cards : hover avec `border-color` violet, `border-radius: 14px`
- Features : icônes SVG dans box `rgba(124,116,255,0.12)`, plus d'emojis
- Footer : copyright mis à jour
- Supprimer les styles inline → tout dans le `<style>` du head

---

## 4. Écran Auth (`#screen-auth` dans `index.html` + CSS)

**Changements :**
- Background : gradient radial violet en haut `radial-gradient(ellipse at 50% 0%, rgba(124,116,255,0.1), transparent 60%)`
- Auth card : `border-radius: 20px`, `border: 1px solid rgba(255,255,255,0.08)`, `box-shadow` profond
- Logo : icône SVG shield dans carré gradient (identique landing)
- Champs : focus ring violet `0 0 0 3px rgba(124,116,255,0.1)`
- Bouton submit : gradient + `box-shadow` teinté
- Note confidentialité : icône SVG lock + texte

---

## 5. App — Header

**Changements :**
- Logo : même icône SVG shield que landing (cohérence totale)
- Tagline : texte mis à jour avec accents corrects
- Boutons header (dashboard, sécurité, thème) : icônes SVG, `width/height: 32px`, hover violet
- User pill : avatar initiales + email tronqué
- Fond header : `rgba(10,10,20,0.9)` + `backdrop-filter: blur(16px)`

---

## 6. App — Pipeline steps

**Changements :**
- Step "done" : `background: #10b981` + checkmark SVG (pas ✓ texte)
- Step "active" : fond `rgba(124,116,255,0.1)`, border radius 8px
- Arrows : SVG chevron-right au lieu de `→` texte

---

## 7. App — Sidebar

**Changements :**
- Doc items : icône SVG file-text dans box, plus d'emojis
- Badges statuts : `badge-ready` (vert), `badge-processing` (orange), `badge-failed` (rouge), `badge-uploaded` (gris)
- Bouton "+ Nouveau" : gradient violet
- Count badge sur "Documents" : pill violette
- Scrollbar stylisée (webkit)

---

## 8. App — Dashboard

**Changements :**
- KPI cards : icônes SVG dans box colorée par type (violet/vert/orange/rouge)
- Ajout delta (↑ +X cette semaine) sous chaque KPI
- GDPR ring : `stroke` vert si score ≥ 85, orange si ≥ 70, rouge sinon
- Bars de risque : couleurs sémantiques (vert/orange/rouge/dark-red)
- Graphe activité 7j : barres SVG ou divs stylisées avec hover state
- Titres de section avec icône SVG inline

---

## 9. App — Upload panel

**Changements :**
- Zone drag & drop : `border: 2px dashed rgba(124,116,255,0.25)`, icône SVG cloud-upload
- Labels uppercase 11px au lieu de labels ordinaires
- Bouton démo : gradient violet
- Format badges : `fmt` pills grises + noms sans emoji
- Checkbox : `accent-color: var(--accent)`

---

## 10. Vérification Railway

**Checklist à valider post-implémentation :**

1. **Health endpoint** — `GET /api/v1/health` répond 200 avec `{"status":"ok"}`
2. **Route UI** — `GET /ui` retourne `index.html` avec nonce CSP correct
3. **Route landing** — `GET /` retourne `landing.html`
4. **Static files** — `/static/css/style.css` et `/static/js/app.js` servis avec bon content-type
5. **Auth** — login, logout, forgot password fonctionnels
6. **Upload** — upload d'un fichier PDF déclenche le pipeline Celery
7. **Anonymisation** — statut passe de `uploaded` → `processing` → `ready`
8. **Dashboard stats** — `GET /api/v1/stats/dashboard` retourne données avec `gdpr_score`
9. **PDF audit report** — `GET /api/v1/documents/{id}/audit-report-pdf` retourne un PDF
10. **CSP nonce** — aucun `style-src 'unsafe-inline'` violation dans la console

---

## 11. Ce qui ne change PAS

- Aucune modification de la logique backend (routes FastAPI, services, modèles)
- Aucune dépendance externe ajoutée (pas de framework CSS, pas d'icon library npm)
- Aucun changement au `app.js` sauf remplacement des emojis injectés dynamiquement
- Mode light existant conservé (variables déjà définis dans `:root.theme-light`)
- Service Worker et manifest inchangés
- `security.html` hors périmètre (page statique, peu visible)

---

## 12. Ordre d'implémentation recommandé

1. Mettre à jour les tokens CSS dans `style.css`
2. Remplacer tous les emojis par SVG dans `index.html` et `style.css`
3. Ajouter Inter font dans `index.html`
4. Refondre `landing.html` (CSS inline → cohérent avec l'app)
5. Polir auth card
6. Polir header + sidebar + dashboard
7. Polir upload panel
8. Passer la checklist Railway
