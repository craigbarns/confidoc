# ConfiDoc - Setup rapide local

## Prerequis

- Python 3.11+
- Docker Desktop (ou moteur Docker compatible)

## 1) Creer un environnement virtuel

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2) Installer le projet

```bash
pip install -e ".[dev,processing]"
```

## 3) Configurer l'environnement

```bash
cp .env.example .env
```

Puis ajuster les variables sensibles dans `.env` (DB, Redis, MinIO, JWT, etc.).

## 4) Demarrer l'infrastructure locale

```bash
docker compose up -d
```

## 5) Appliquer les migrations

```bash
alembic upgrade head
```

## 6) Lancer l'API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 7) Verification rapide

```bash
curl http://localhost:8000/health
curl http://localhost:8000/readiness
```

Objectif attendu:
- `/health` -> `healthy`
- `/readiness` -> `ready`
