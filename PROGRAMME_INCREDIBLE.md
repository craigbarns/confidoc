# Programme « Incroyable » — ConfiDoc

Vision : **confiance mesurable**, **clarté pour le métier**, **opérations sereines**.

---

## Piliers

### 1. Confiance (qualité)
- [x] Garde-fous P1/P2 (bilan, compte de résultat) avec tolérances et `minor_gap`
- [x] Smart split + **repli texte intégral** si meilleure qualité
- [x] Couche **`experience`** : niveau, phrase clé FR, items détaillés, note découpe
- [x] **`experience.traceability`** : écarts / tolérances bilan & chaîne CR (nombres)
- [x] Jeux **golden synthétiques** (`tests/golden/`) — régression sans PDF
- [x] Dossier **`golden/`** : schéma JSON (`golden_schema.json`), exemple `golden_sets.minimal.json`, `python scripts/validate_golden_sets.py` + CI
- [x] **`golden/regression_fixtures.json`** + `app/golden/compare.py` + tests non-régression sur **valeurs** extraites ; `scripts/run_golden_regression.py`
- [ ] Dashboard interne KPI (hors scope backend seul)

### 2. Clarté (UX & API)
- [x] `export-structured-dataset` inclut `experience`
- [x] `dataset-summary` expose `experience` pour l’UI
- [x] UI : synthèse « expérience » dans la carte qualité
- [x] **`GET /audit-quality-bundle`** : JSON archivage (hash document + qualité + experience, sans texte brut)
- [ ] Export **PDF** rapport (nécessite lib dédiée — à planifier)
- [ ] Comparaison **deux documents** côté API (à planifier)

### 3. Fiabilité pipeline
- [x] CI GitHub Actions (pytest + deps dev complètes)
- [x] Scripts smoke / post-déploiement
- [x] **Seuils optionnels** smoke : `CONFIDOC_SMOKE_MIN_COVERAGE_BILAN`, `_CR`, `_2072`
- [x] **Webhook** post-validation : `WEBHOOK_ON_VALIDATE_URL` (+ secret HMAC optionnel)

### 4. PDF & contenu long
- [x] Fenêtre sémantique V1 (mots-clés)
- [x] **Marqueurs de page** `---PAGE N---` (extraction native + OCR) ; préfixe `---PDF N PAGES---` pour sortie markdown
- [x] Compteur **`pdf_page_markers_in_source`** dans `provenance.text_segmentation`
- [ ] Routeur **multi-sections** dédié (évolution)

### 5. Différenciation
- [x] Traçabilité **numérique** (écarts, tolérances) dans `experience.traceability`
- [x] **Preuve** : `audit-export` + `audit-quality-bundle` + SHA256 document
- [ ] SLA contractuel / page statut (produit)

---

## Variables d’environnement (extraits)

| Variable | Rôle |
|----------|------|
| `PDF_PAGE_MARKERS` | `true`/`false` — marqueurs de page dans le texte extrait |
| `WEBHOOK_ON_VALIDATE_URL` | URL POST `{event, document_id}` après validation |
| `WEBHOOK_ON_VALIDATE_SECRET` | Secret HMAC-SHA256 (`X-ConfiDoc-Signature: sha256=...`) |
| `CONFIDOC_SMOKE_MIN_COVERAGE_BILAN` | Seuil optionnel pour `e2e_smoke` (idem `_CR`, `_2072`) |

---

## Indicateurs à suivre (hebdo)

| Indicateur | Cible directionnelle |
|------------|------------------------|
| `ready_for_ai` sur jeu ref. | ↑ |
| `critical_missing_fields` non vides | ↓ |
| `bilan_balance_mismatch` sur plaquettes connues | ↓ ou documenté |
| Temps moyen jusqu’à validation humaine | ↓ |

---

*Document vivant — à ajuster avec les retours terrain.*
