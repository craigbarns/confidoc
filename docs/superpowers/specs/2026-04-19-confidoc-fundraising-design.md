# ConfiDoc — Design : App Exceptionnelle pour Levée de Fonds Pre-Seed

**Date :** 2026-04-19  
**Contexte :** Pre-seed, business angels < 500k€. L'investor doit pouvoir tester le produit seul en 60 secondes et repartir convaincu.  
**Approche validée :** Full Stack — démo publique + landing refonte + améliorations app

---

## 1. Démo publique sans login

### Problème
`POST /api/v1/demo` exige `CurrentUser`. Tous les CTA de la landing pointent vers `/ui` (mur de login). Un investor ne peut rien tester sans credentials.

### Solution
Ajouter `GET /api/v1/demo/public` — endpoint sans authentification qui retourne un résultat de démo pré-calculé.

**Comportement :**
- Aucune auth requise
- Rate-limit : 10 req/min/IP (via `app/rate_limit.py`)
- Le résultat de démo est **pré-calculé au démarrage du serveur** (startup event FastAPI) et stocké en Redis sans TTL
- `GET /api/v1/demo/public` sert uniquement depuis le cache Redis — jamais de calcul synchrone en requête
- Si le cache est absent (premier démarrage avant que le worker ait fini), retourne HTTP 202 + `{"status": "warming_up"}` — le frontend affiche un spinner 3s puis réessaie
- Retourne : texte original, texte anonymisé, entités détectées (type + position), score RGPD, champs extraits

**Fichiers modifiés :**
- `app/api/v1/demo.py` — nouveau endpoint `GET /public` (sans auth)
- `app/services/demo_service.py` (nouveau) — logique de calcul + cache Redis + startup warm-up
- `app/rate_limit.py` — règle dédiée `/api/v1/demo/public`
- `app/templates/landing.html` — bloc "Live Demo" inline

**Sécurité :**
- Seul `demo_doc.pdf` est traité — aucun upload utilisateur possible
- Résultat en lecture seule, aucune écriture en base
- Rate-limit IP empêche l'abus

---

## 2. Refonte landing page

### Structure (de haut en bas)

**Bloc 1 — Hero**
- Titre : "L'IA comptable sans exposer vos données clients"
- 3 métriques inline (statiques pour commencer, ex: "2 400 docs traités · 94% Full Ready · < 12s/doc")
- 2 CTA : "Tester maintenant" (ancre vers bloc démo) · "Espace client" (→ `/ui`)
- Remplacement de l'image manquante par un mockup HTML inline (split original/anonymisé)

**Bloc 2 — Live Demo inline** *(nouveau, le cœur de la page)*
- Bouton "Lancer la démo" → appel `GET /api/v1/demo/public`
- Affiche side-by-side : texte original / texte anonymisé avec entités colorées
- Score RGPD affiché en bas
- CTA de conversion : "Traiter vos propres documents →" (→ `/ui`)

**Bloc 3 — Social proof**
- Bande "Conçu pour les cabinets d'expertise comptable et avocats"
- Badges : RGPD · Made in France · Données hébergées en Europe

**Bloc 4 — Comment ça marche**
- Conserver les 3 étapes existantes, réécrire les textes moins techniques

**Bloc 5 — Tarification** *(nouveau)*
- Starter : gratuit, 10 docs/mois
- Pro : 49 €/mois, 200 docs/mois
- Cabinet : sur devis, illimité + intégration SI
- Objectif : montrer le modèle de monétisation aux angels

**Bloc 6 — CTA final**
- Remplacer "Prendre rendez-vous" → `/ui` par `mailto:gregory@superhome.fr` ou lien Calendly
- Ajouter formulaire capture email "Rejoindre la beta"

**Fixes immédiats :**
- CTA "Prendre rendez-vous pour une démo" → `/ui` → remplacer par contact réel
- Image hero `.dashboard-preview img` absente → remplacer par mockup HTML
- Footer "ConfiDoc SAS" sans mentions légales → ajouter `/legal` minimale

---

## 3. Améliorations de l'app

### 3.1 Onboarding guidé au premier login
- Détecter si l'user n'a aucun document (dashboard stats = 0)
- Afficher un banner prominent : "👋 Bienvenue — Testez en 1 clic avec un vrai document comptable"
- Bouton "▶ Lancer la démo maintenant" → appelle `POST /api/v1/demo` (endpoint existant, avec auth cette fois)
- Polling toutes les 2s sur `GET /api/v1/documents/{id}` jusqu'à status `ready`
- Ouvre automatiquement le panel Anonymisation avec le document chargé
- L'investor est dans le flow en moins de 15 secondes

**Fichiers :** `app/templates/index.html` (banner + JS onboarding), `app/static/js/app.js`

### 3.2 Page /investor — métriques plateforme
- Nouvelle route `GET /investor` → template `investor.html`
- Endpoint API `GET /api/v1/stats/platform` (sans auth, données agrégées uniquement) :
  - `total_documents_processed` — total cumulé
  - `full_ready_rate` — % docs Full Ready
  - `avg_entities_per_doc` — entités masquées en moyenne
  - `avg_processing_seconds` — temps moyen pipeline
- Page simple, élégante, partageable (lien direct pour le pitch deck)

**Fichiers :** `app/api/v1/_doc_stats.py` (endpoint platform), `app/templates/investor.html` (nouveau), `app/main.py` (route `/investor`)

### 3.3 Split-view immédiat post-anonymisation
- Actuellement : le split original/anonymisé s'affiche mais nécessite une interaction
- Modification : dès que `status = ready`, ouvrir automatiquement `#anon-split-view` avec les entités surlignées par type (couleurs existantes dans le design system)
- Rendre visible le `risk-indicator` immédiatement dans la barre de stats

**Fichiers :** `app/static/js/app.js` (logique de polling post-anonymisation)

### 3.4 Score RGPD inline sur le document
- Ajouter dans `#anon-doc-bar` (la barre de contexte du document) un badge :  
  `Score RGPD : 94 · Full Ready ✓` ou `Score RGPD : 67 · Review requis`
- Les données sont déjà disponibles dans la réponse API d'anonymisation

**Fichiers :** `app/templates/index.html` (badge dans anon-doc-bar), `app/static/js/app.js`

---

## 4. Hors scope

- Système de paiement réel (les prix de la page tarification sont indicatifs)
- Internationalisation (EN)
- Refonte du CSS global / design system
- Nouveaux types de documents

---

## 5. Ordre d'implémentation recommandé

1. `GET /api/v1/demo/public` + cache Redis (backend, indépendant)
2. Landing — bloc Live Demo inline (dépend du point 1)
3. Landing — hero fixes + tarification + CTA (indépendant)
4. App — onboarding banner + flow auto-demo (frontend)
5. App — score RGPD inline + split-view immédiat (frontend, rapide)
6. Page `/investor` + endpoint platform stats (backend + frontend)
