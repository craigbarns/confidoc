# ConfiDoc

**Plateforme de pseudonymisation et anonymisation assistee, avec controle humain, journal d'audit, et regles sectorielles comptables/juridiques.**

ConfiDoc aide les cabinets comptables et professions reglementees a traiter des documents sensibles (bilans, declarations fiscales, liasses) en conformite RGPD, en distinguant clairement pseudonymisation et anonymisation forte.

### Approche RGPD

| | Pseudonymisation | Anonymisation forte |
|---|---|---|
| **Usage** | Travail interne, revue, reprise | Export, IA tierce, demo, partage |
| **Donnees** | Restent des donnees personnelles (RGPD s'applique) | Hors champ RGPD si risque de reidentification elimine |
| **Tokens** | Reversibles avec cle ([PERSONNE_1]) | Masquage fort + quasi-identifiants |
| **Controle** | Revue humaine possible | Score de risque de reidentification |

## Fonctionnalites principales

- **Deux modes RGPD** : pseudonymisation (interne) et anonymisation forte (export/IA) avec scoring de risque de reidentification
- **Score de reidentification** : analyse automatique des quasi-identifiants residuels, combinaisons, et risque de recoupement (CNIL)
- **Journal d'audit RGPD** : tracabilite horodatee des uploads, exports, validations, OCR, anonymisation, scoring et etapes systeme
- **Trust Score / AI Readiness Score** : score visible par document et au dashboard pour savoir si le document est exploitable par IA
- **Anonymisation automatique** : detection et masquage des identifiants directs (noms, SIRET, IBAN, emails) et indirects (adresses, filiales, pourcentages, refs locales)
- **Extraction structuree** : extraction automatique des champs comptables (actif, passif, CA, resultat) avec scoring de qualite
- **Types de documents** : bilan, compte de resultat, declaration 2072, releve bancaire, liasse simplifiee
- **Validation humaine** : workflow de revue avec capture de feedbacks pour amelioration continue
- **Exports multiples** : JSON structure, rapport DOC/PDF, PDF redacte
- **AI assistee** : resume et audit via Mistral Large (LLM) et Mistral OCR
- **Privacy by design** : collecte minimale, separation des usages, chiffrement, controle d'acces, suppression securisee
- **Golden Sets** : 250+ cas de test de regression pour garantir la qualite d'extraction

## Stack technique

| Couche | Technologies |
|--------|-------------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Base de donnees | PostgreSQL 16 (async SQLAlchemy 2.0) |
| Cache | Redis 7+ |
| Stockage | MinIO/S3, local, database fallback |
| Auth | JWT (HS256), bcrypt |
| NLP | spaCy, Presidio, PyMuPDF, pytesseract |
| Tests | pytest, pytest-asyncio, golden sets |
| CI/CD | GitHub Actions, Docker, Railway |

## Demarrage rapide

### Prerequis

- Python 3.11+
- PostgreSQL 16+
- Redis 7+

### Installation

```bash
# Cloner le projet
git clone https://github.com/craigbarns/confidoc.git
cd confidoc

# Creer un environnement virtuel
python -m venv .venv
source .venv/bin/activate

# Installer les dependances
pip install -e ".[dev]"

# Copier la configuration
cp .env.example .env
```

### Lancer avec Docker Compose

```bash
docker-compose up -d   # PostgreSQL, Redis, MinIO
uvicorn app.main:app --reload --port 8000
```

### Lancer les tests

```bash
# Tests unitaires et API
pytest tests/ -q

# Avec couverture
pytest tests/ --cov=app --cov-report=term-missing

# Validation des golden sets
python scripts/validate_golden_sets.py golden/golden_sets.minimal.json
```

## Architecture

```
app/
  api/v1/        # Endpoints FastAPI (auth, uploads, documents, AI, KB, feedback)
  services/      # Logique metier (anonymisation, extraction, qualite)
  models/        # ORM SQLAlchemy
  schemas/       # Pydantic (validation entree/sortie)
  core/          # Utilitaires (database, securite, logging, middleware)
  middleware.py  # Request ID, security headers, timing
tests/           # Unit, API, integration, golden sets
golden/          # Cas de test de reference (~250+)
scripts/         # Automatisation
```

## API

L'API est documentee via Swagger UI : `http://localhost:8000/docs`

### Endpoints principaux

| Methode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/v1/auth/login` | Authentification |
| POST | `/api/v1/uploads` | Upload de document |
| POST | `/api/v1/documents/{id}/anonymize` | Anonymiser un document |
| GET | `/api/v1/documents/{id}/preview` | Preview de l'anonymisation |
| POST | `/api/v1/documents/{id}/validate` | Valider et figer la version finale |
| GET | `/api/v1/documents/{id}/structured` | JSON IA/RAG : entités, tags sémantiques, texte anonymisé (`?include_text=`) |
| GET | `/api/v1/documents/{id}/risk-score` | Risque RGPD, Trust Score et AI Readiness Score |
| GET | `/api/v1/documents/{id}/audit-report` | Journal d'audit et preuve de traitement |
| GET | `/api/v1/stats/quality-dashboard` | Qualite, validation humaine, golden drafts et readiness IA |
| GET | `/health` | Health check |
| GET | `/readiness` | Readiness probe |
| GET | `/version` | Version applicative et metadata Railway non sensibles |

## Production readiness

ConfiDoc bloque le demarrage en production si des secrets restent aux valeurs par defaut ou si `STORAGE_BACKEND=local`.

Variables minimales a fournir en production :

- `APP_ENV=production`
- `SECRET_KEY`, `JWT_SECRET_KEY`, `ENCRYPTION_MASTER_KEY`, `PSEUDO_MAPPING_KEY`
- `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `STORAGE_BACKEND=minio` ou `database`
- `ALLOWED_ORIGINS` limite aux domaines reels du front
- `BOOTSTRAP_SECRET` pour l'initialisation admin controlee

Checks operationnels :

- `GET /health` : liveness rapide.
- `GET /readiness` : PostgreSQL, Redis, stockage; Celery est `skipped` en mono-service et sonde uniquement si `DOCUMENT_PROCESSING_BACKEND=celery`.
- `GET /version` : version, environnement et metadata Railway non sensibles.
- Docker : healthcheck integre sur `/health`.
- Audit : les details sensibles sont minimises, les champs suspects sont hashes, et chaque entree recoit un `event_hash`.

### Railway production checklist

- Configurer `APP_ENV=production` et `APP_VERSION`.
- Configurer `DEBUG=false`.
- Fournir `DATABASE_URL` PostgreSQL Railway et `REDIS_URL` Redis Railway.
- Fournir `SECRET_KEY`, `JWT_SECRET_KEY`, `ENCRYPTION_MASTER_KEY`, `PSEUDO_MAPPING_KEY`, `BOOTSTRAP_SECRET`.
- Utiliser `STORAGE_BACKEND=database` pour un premier pilote Railway simple, ou `STORAGE_BACKEND=minio` avec bucket S3/R2/MinIO persistant; `local` est bloque en production.
- Restreindre `ALLOWED_ORIGINS` au domaine Railway/front reel.
- Garder `DOCUMENT_PROCESSING_BACKEND=api` pour les pilotes mono-service; ne passer a `celery` que si des workers dedies sont réellement deployes.
- Lancer les migrations Alembic avant demo client : `alembic upgrade head`.
- Tests locaux avant deploy : `pytest tests/ -q` puis `ruff check app tests scripts`.
- Smoke test post-deploy : `python scripts/smoke_test.py --base-url https://VOTRE-APP.up.railway.app`.
- Smoke test avec compte demo : `CONFIDOC_DEMO_EMAIL=demo@confidoc.fr CONFIDOC_DEMO_PASSWORD=... python scripts/smoke_test.py --base-url https://VOTRE-APP.up.railway.app`.
- Verifier `/health`, `/readiness`, `/version` apres deploy.
- Si `scripts/seed.py` est utilise en production, fournir `CONFIDOC_SEED_ADMIN_PASSWORD`.

Variables Railway obligatoires pour une demo live :

- `APP_ENV=production`
- `DEBUG=false`
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `ENCRYPTION_MASTER_KEY`
- `PSEUDO_MAPPING_KEY`
- `BOOTSTRAP_SECRET`
- `ALLOWED_ORIGINS`
- `STORAGE_BACKEND`
- `DOCUMENT_PROCESSING_BACKEND=api` pour une demo mono-service, `celery` seulement si workers Railway dedies.

Preset Railway "demo standard" :

- `DOCUMENT_PROCESSING_BACKEND=api`
- `DEMO_MODE=true`
- `DEMO_SEED_ENABLED=true`
- `SENSITIVE_CLIENT_MODE=false`
- `MISTRAL_ENABLED=true` si la demo utilise l'OCR/IA externe.

Preset Railway "cabinet sensible" :

- `DOCUMENT_PROCESSING_BACKEND=api`
- `DEMO_MODE=true` ou `false` selon le contexte commercial.
- `SENSITIVE_CLIENT_MODE=true`
- `MISTRAL_ENABLED=false` si le client refuse tout appel IA externe.
- `OLLAMA_ENABLED=false` par defaut; activer une IA locale seulement avec une infrastructure dediee.
- Ne pas activer Celery tant que les temps de traitement des pilotes ne le justifient pas.

Checklist avant demo investisseur :

- `alembic upgrade head` execute.
- `/health` retourne `healthy`.
- `/readiness` retourne `ready`.
- `/version` affiche la version, la branche et la policy IA sans secret.
- Bouton `Charger une démo` disponible sur le dashboard.
- Export `Rapport d'audit PDF` disponible après traitement.
- `SENSITIVE_CLIENT_MODE` positionne selon le contexte client.

### Documentation due diligence

- `docs/ARCHITECTURE.md`
- `docs/SECURITY.md`
- `docs/AI_SECURITY.md`
- `docs/DUE_DILIGENCE.md`
- `docs/ROADMAP_INVESTOR.md`
- `docs/DEMO_SCRIPT.md`

## Positionnement investisseur

La demonstration doit raconter cette sequence :

1. Upload authentifie avec scan, hash SHA-256, stockage non local en production et audit.
2. OCR/extraction puis anonymisation avant tout usage IA.
3. Score RGPD, Trust Score et AI Readiness visibles.
4. Validation humaine et export gates pour les risques eleves.
5. Audit trail et rapport PDF disponibles pour preuve DPO.
6. Tests de non-regression sur anonymisation, extraction et quality dashboard.

## Securite

- Tous les secrets doivent etre configures via variables d'environnement en production
- Rate limiting sur les endpoints d'authentification
- Headers de securite (X-Content-Type-Options, X-Frame-Options, CSP)
- Request ID tracking pour tracabilite
- Comparaison timing-safe des tokens de recovery
- Validation stricte des mots de passe

## Licence

Proprietary - ConfiDoc
