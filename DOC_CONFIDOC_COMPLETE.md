# ConfiDoc - Documentation complete

## 1) Vision et objectif

ConfiDoc est une plateforme de confidentialite documentaire pour cabinets comptables et equipes finance.

Objectif principal:
- transformer des documents comptables sensibles en donnees anonymisees/pseudonymisees exploitables;
- conserver la valeur metier (montants, structures, champs comptables utiles);
- fournir une preuve de traitement (audit/proof) et des sorties JSON fiables;
- permettre des usages IA sur donnees anonymisees uniquement.

---

## 2) Perimetre fonctionnel

### 2.1 Fonctions coeur

- Upload de documents (`pdf`, `png`, `jpg`, `jpeg`, `tiff`)
- Extraction texte (OCR + fallback)
- Anonymisation / pseudonymisation selon profil
- Preview avant validation
- Validation humaine
- Export dataset anonymise
- Export structured dataset metier
- Export audit RGPD
- Export proof d'integrite
- Recherche base anonyme (KB)
- Synthese IA (Ollama) avec fallback securise

### 2.2 Types documentaires cibles (etat actuel)

V1 stable:
- `bilan`
- `compte_resultat`
- `fiscal_2072`

Present mais hors focus V1:
- `liasse_is_simplifiee`
- `fiscal_2044`
- `releve_bancaire`
- `facture_fournisseur`
- `unknown_*` (tax/accounting/other)

---

## 3) Architecture technique

### 3.1 Stack

- Backend: FastAPI
- DB: PostgreSQL (SQLAlchemy async)
- Cache/queue: Redis (Celery)
- Storage: `database`, `local` ou `minio` (selon config)
- IA locale: Ollama (optionnel)
- Deploiement: Railway

### 3.2 Organisation (haut niveau)

- `app/api/health.py`: health/readiness
- `app/api/ui.py`: console web `/ui`
- `app/api/v1/`: endpoints metier (auth, uploads, documents, ai, kb)
- `app/services/`: extraction, anonymisation, datasets, storage
- `scripts/`: smoke tests / automatisation

---

## 4) Flux metier principal

1. Login utilisateur
2. Upload document
3. Anonymisation (auto ou manuelle)
4. Preview
5. Validation humaine
6. Exports:
   - dataset
   - structured dataset
   - audit / proof
7. Usage IA (synthese) sur donnees anonymisees

---

## 5) Contrat JSON structured dataset

Le payload structured dataset expose un contrat commun:

- `doc_type` (type utilise pour l'extraction finale)
- `detected_doc_type` (type detecte par routeur)
- `routing_confidence`
- `routing_confidence_raw`
- `routing_reasons`
- `routing_runner_up`
- `anonymized`
- `generated_at`
- `fields` (dictionnaire de champs metier)
- `tables` (tables metier structurees)
- `quality`
- `provenance`

`quality` est normalise avec au minimum:
- `coverage_ratio`
- `filled_fields`
- `total_fields`
- `needs_review`
- `ready_for_ai`
- `quality_flags`
- `critical_missing_fields`

`provenance` contient:
- version extracteur
- nom extracteur selectionne
- version routeur
- source filename

---

## 6) Registry extracteurs V1

ConfiDoc utilise un registry pour separer logique commune et logique specialisee.

Extracteurs V1 branches:
- `extractor_bilan`
- `extractor_compte_resultat`
- `extractor_2072`

Principe:
- le routeur detecte un type global (`detected_doc_type`);
- la requete peut forcer un `doc_type` pour extraction;
- l'extracteur effectivement utilise est trace dans `provenance.extractor_name`.

---

## 7) API principale (resume)

Base:
- `/health`
- `/readiness`
- `/ui`

Auth (`/api/v1/auth`):
- `POST /login`
- `POST /refresh`
- `POST /logout`
- `POST /bootstrap-admin`
- `POST /recover-access`

Uploads:
- `POST /api/v1/uploads?auto_anonymize=true&profile=...&document_type=...`

Documents (`/api/v1/documents/{id}`):
- `POST /anonymize`
- `GET /preview`
- `POST /validate`
- `GET /export-dataset`
- `GET /export-structured-dataset?doc_type=...`
- `GET /audit-export`
- `GET /proof`
- `GET /dataset-summary`
- `DELETE /`

AI:
- `POST /api/v1/ai/summary/{id}`

KB:
- endpoints recherche/ingestion base anonyme

---

## 8) UI console `/ui`

Actions document:
- `Traiter tout`
- `Anonymiser`
- `Previsualiser`
- `Valider`
- `Exporter le dataset`
- `Dataset metier`
- `Synthese IA`
- `Exporter la preuve`
- `Exporter l'audit`
- `Supprimer`

Panneaux importants:
- Preview
- Ce qui a ete masque
- Reponse API brute (debug)
- Question a la base anonyme

---

## 9) Configuration environnement

Variables critiques:
- `APP_ENV`
- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `STORAGE_BACKEND` (`database` recommande sur Railway sans MinIO)
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `ENCRYPTION_MASTER_KEY`
- `ADMIN_RECOVERY_TOKEN` (si utilise)

Storage:
- sans MinIO: `STORAGE_BACKEND=database` ou `local`
- avec MinIO/S3-compatible: renseigner `MINIO_*`

---

## 10) Health / readiness

`/health`:
- verifie que l'application repond.

`/readiness`:
- verifie DB + Redis
- verifie storage si backend MinIO
- passe `storage=skipped` si storage non-MinIO

Objectif prod:
- `status: ready`
- checks critiques en `ok` (ou `storage: skipped` si architecture sans MinIO)

---

## 11) Tests et validation

### 11.1 Tests unitaires

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
```

### 11.2 Smoke E2E simple

```bash
CONFIDOC_BASE_URL="https://confidoc-production.up.railway.app" \
CONFIDOC_EMAIL="admin@confidoc.fr" \
CONFIDOC_PASSWORD='***' \
CONFIDOC_TEST_FILE="/chemin/document.pdf" \
./scripts/e2e_smoke.sh --compact
```

Sortie compacte attendue:
- `PASS/FAIL`
- `routing_requested`
- `routing_selected`
- `extractor_selected`
- `doc_type`
- `needs_review`
- `coverage_ratio`
- `quality_flags`
- `critical_missing_fields`

### 11.3 Matrix extracteurs V1

```bash
CONFIDOC_BASE_URL="https://confidoc-production.up.railway.app" \
CONFIDOC_EMAIL="admin@confidoc.fr" \
CONFIDOC_PASSWORD='***' \
CONFIDOC_TEST_FILE_BILAN="/chemin/bilan.pdf" \
CONFIDOC_TEST_FILE_COMPTE_RESULTAT="/chemin/compte_resultat.pdf" \
CONFIDOC_TEST_FILE_FISCAL_2072="/chemin/2072.pdf" \
./scripts/extractor_smoke_matrix.sh
```

---

## 12) Lecture des metriques qualite

- `coverage_ratio`: taux de champs remplis
- `needs_review`: revue humaine recommandee
- `quality_flags`: drapeaux de risque (ex. `uppercase_person_leftovers`)
- `critical_missing_fields`: champs metier critiques absents
- `routing_confidence`: confiance du routeur

Interpretation conseillee:
- haut `coverage_ratio` + peu de flags = bon candidat IA
- `needs_review=true` = validation humaine avant usage metier sensible

---

## 13) Securite et RGPD

Principes:
- anonymisation avant usage IA
- minimisation des donnees
- audit/proof exportables
- pas de texte brut expose dans les exports audit

Synthese IA:
- executee sur donnees anonymisees
- fallback local en cas de reponse LLM vide/non exploitable

---

## 14) Runbook incidents (operations)

### Cas A - `readiness: degraded`

1. verifier `DATABASE_URL` / `REDIS_URL`
2. verifier que Redis est reachable depuis Railway
3. verifier mode storage (`STORAGE_BACKEND`)
4. si MinIO actif: verifier `MINIO_ENDPOINT`, creds, bucket

### Cas B - E2E fail sur `anonymize`

1. verifier le type/qualite du fichier test
2. verifier logs backend Railway
3. retester avec un document de reference stable

### Cas C - `extractor_selected=unknown`

1. verifier que le dernier commit est bien deployee
2. verifier la reponse `export-structured-dataset` contient `provenance.extractor_name`

---

## 15) Roadmap recommandee

Vague 1 (en cours):
- bilan
- compte_resultat
- fiscal_2072

Vague 2:
- fiscal_2044
- balance
- grand_livre

Vague 3:
- releves bancaires
- factures
- autres docs comptables recurrents

Strategie:
- socle commun stable
- extracteurs specialises ajoutes progressivement
- validation matrix par type documentaire

---

## 16) Fichiers de reference dans le repo

- `SETUP_QUICKSTART.md`
- `RAILWAY_ENV_CHECKLIST.md`
- `BETA_TEST_API.md`
- `DOCUMENTATION_COMPTABLE.md`
- `SECURITY_POLICY_ENGINE.md`
- `scripts/e2e_smoke.sh`
- `scripts/extractor_smoke_matrix.sh`

---

## 17) Definition de done (production-ready)

Un type documentaire est considere "production-ready" quand:
- le routing est stable sur jeux de test reels
- `extractor_selected` est observable
- coverage acceptable metier
- flags critiques sous controle
- e2e smoke PASS reproductible apres deploiement
- audit/proof conformes et exploitables

