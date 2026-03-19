.PHONY: help install dev infra infra-down migrate migrate-new test lint format run worker

help: ## Afficher l'aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Installer les dépendances
	pip install -e ".[dev,processing]"

dev: ## Lancer le serveur de développement
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

infra: ## Démarrer l'infrastructure (Postgres, Redis, MinIO)
	docker compose up -d

infra-down: ## Arrêter l'infrastructure
	docker compose down

infra-reset: ## Reset complet de l'infrastructure (supprime les données)
	docker compose down -v
	docker compose up -d

migrate: ## Appliquer les migrations
	alembic upgrade head

migrate-new: ## Créer une nouvelle migration (usage: make migrate-new msg="description")
	alembic revision --autogenerate -m "$(msg)"

test: ## Lancer les tests
	pytest -v --cov=app --cov-report=term-missing

lint: ## Vérifier le code
	ruff check app/ tests/
	mypy app/

format: ## Formater le code
	ruff check --fix app/ tests/
	ruff format app/ tests/

run: infra dev ## Démarrer infra + serveur dev

worker: ## Lancer le worker Celery
	celery -A app.workers.celery_app worker --loglevel=info -Q ingestion,ocr,processing,rendering,export,maintenance,notifications

flower: ## Lancer Flower (monitoring Celery)
	celery -A app.workers.celery_app flower --port=5555

setup-env: ## Créer le fichier .env depuis le template
	@if [ ! -f .env ]; then cp .env.example .env && echo "✅ .env créé depuis .env.example"; else echo "⚠️  .env existe déjà"; fi
