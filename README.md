# ConfiDoc

**Backend SaaS de confidentialisation documentaire pour cabinets comptables et professions reglementees.**

ConfiDoc transforme des documents sensibles (bilans, comptes de resultat, declarations fiscales) en datasets anonymises exploitables par l'IA, tout en preservant la valeur metier et en garantissant la conformite RGPD.

## Fonctionnalites principales

- **Anonymisation automatique** : detection et masquage des donnees personnelles (noms, SIRET, IBAN, emails) via NLP (spaCy, Presidio)
- **Extraction structuree** : extraction automatique des champs comptables (actif, passif, CA, resultat) avec scoring de qualite
- **Types de documents** : bilan, compte de resultat, declaration 2072, releve bancaire, liasse simplifiee
- **Validation humaine** : workflow de revue avec capture de feedbacks pour amelioration continue
- **Exports multiples** : JSON structure, rapport DOC/PDF, PDF redacte
- **AI assistee** : resume et audit via Ollama (LLM local), Mistral, ou Hugging Face
- **Base de connaissances** : ingestion et recherche sur les donnees anonymisees
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
| GET | `/health` | Health check |
| GET | `/readiness` | Readiness probe |

## Securite

- Tous les secrets doivent etre configures via variables d'environnement en production
- Rate limiting sur les endpoints d'authentification
- Headers de securite (X-Content-Type-Options, X-Frame-Options, CSP)
- Request ID tracking pour tracabilite
- Comparaison timing-safe des tokens de recovery
- Validation stricte des mots de passe

## Licence

Proprietary - ConfiDoc
