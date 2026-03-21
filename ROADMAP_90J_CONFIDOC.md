# ROADMAP 90 Jours - ConfiDoc

## 1) Objectif global

Passer de "pipeline fonctionnel" a "plateforme extracteurs comptables robuste et pilotable par KPI".

Resultat attendu a 90 jours:
- V1 fiable sur `bilan`, `compte_resultat`, `fiscal_2072`
- qualite mesurable et stable en production
- runbook ops + regression automatique apres chaque deploiement

---

## 2) KPIs de reference

### 2.1 KPIs qualite extraction

- `coverage_ratio` median par type
- `% documents needs_review`
- `% documents avec quality_flags non vide`
- `% documents avec critical_missing_fields non vide`

### 2.2 KPIs fiabilite pipeline

- taux de succes `e2e_smoke --compact`
- taux de succes `extractor_smoke_matrix`
- taux d'erreur 5xx sur `/anonymize` et `/export-structured-dataset`

### 2.3 KPIs observabilite

- `% runs avec extractor_selected renseigne`
- `% runs avec routing_requested/routing_selected/doc_type coherents`

---

## 3) Cibles chiffrées a 90 jours

- `extractor_selected` renseigne: >= 99%
- e2e smoke post-deploy: 100% sur jeu de reference
- `coverage_ratio` median:
  - bilan >= 0.60
  - compte_resultat >= 0.65
  - fiscal_2072 >= 0.50
- `needs_review`:
  - baisse d'au moins 25% vs baseline actuelle
- `uppercase_person_leftovers`:
  - baisse d'au moins 50% vs baseline actuelle

---

## 4) Plan 30/60/90 jours

## J+30 - Stabilisation V1

### Objectifs

- fiabiliser extraction V1 sans regression
- stabiliser observabilite et tests post-deploiement

### Chantiers

1. Qualite 2072 (prioritaire)
   - renforcer champs critiques:
     - `frais_charges_hors_interets`
     - `interets_emprunts`
     - `revenu_net_foncier`
   - fallback annexes + calcul derive controle

2. Reduction `uppercase_person_leftovers`
   - heuristiques progressives
   - whitelist metier (libelles comptables, en-tetes formulaires)

3. Validation automatique
   - imposer run post-deploy:
     - `./scripts/e2e_smoke.sh --compact`
     - `./scripts/extractor_smoke_matrix.sh`

4. Observabilite
   - tracer clairement:
     - `routing_requested`
     - `routing_selected`
     - `extractor_selected`
     - `doc_type`

### Go/No-Go J+30

Go si:
- matrix V1 passe 3/3 sur jeu de reference
- pas de 5xx recurrent sur anonymize/export structured
- `extractor_selected` non `unknown`

No-Go sinon:
- freeze features
- sprint correctif qualite/extraction

---

## J+60 - Industrialisation qualite

### Objectifs

- sortir du debug ad hoc et passer en pilotage par jeu d'or
- fiabiliser documents mixtes (plaquettes multi-sections)

### Chantiers

1. Golden set
   - constituer 10-20 docs par type V1
   - definir attendu JSON metier valide comptable

2. Tests de non-regression extraction
   - comparer sortie courante vs attendu
   - seuils toleres sur montants/champs

3. Section-aware extraction
   - detecter zones `bilan` et `compte_resultat` dans un meme PDF
   - extraction par section, pas uniquement globale document

4. UI metier "Pourquoi a revoir"
   - afficher:
     - `quality_flags`
     - `critical_missing_fields`
   - recommandations de correction ciblees

### Go/No-Go J+60

Go si:
- regression V1 stable sur golden set
- baisse mesurable de `needs_review` et flags

No-Go sinon:
- limiter scope V2
- renforcer heuristiques V1

---

## J+90 - Plateforme prete extension V2

### Objectifs

- socle V1 solide, mesurable, operable
- ouverture V2 sans dette critique

### Chantiers

1. Hardening operations
   - dashboard KPI extraction + erreurs API
   - alerting basique sur degradation readiness et 5xx

2. Process de release
   - checklist release standard
   - gate qualite obligatoire avant merge/deploy

3. Preparation V2 extracteurs
   - cadrage `fiscal_2044`, `balance`, `grand_livre`
   - contrat JSON deja compatible

### Go/No-Go J+90

Go si:
- objectifs chiffrés V1 atteints (ou proche avec tendance robuste)
- process release + monitoring en place

No-Go sinon:
- prolonger stabilisation V1
- reporter extension V2

---

## 5) Backlog priorisé

### P0 (immédiat)

- corriger `uppercase_person_leftovers`
- combler `critical_missing_fields` 2072 prioritaires
- s'assurer que `extractor_selected` est toujours present en prod

### P1 (court terme)

- golden set V1
- tests non-regression extracteurs
- UI "Pourquoi a revoir" exploitable comptable

### P2 (moyen terme)

- section-aware parsing documents mixtes
- optimisation routeur multi-signaux
- runbook incident detaille par endpoint

---

## 6) Rituels hebdomadaires recommandés

- revue KPI hebdo (30 min)
- revue 5 docs "A revoir" avec comptable metier
- suivi trend:
  - coverage
  - flags
  - critical_missing
  - needs_review

---

## 7) Definition de done par extracteur V1

Un extracteur est "done" quand:
- regression tests verts sur jeu d'or
- champs critiques stables
- `needs_review` en baisse durable
- pas de 5xx sur parcours E2E
- lisibilite metier validee par utilisateur comptable

