#!/bin/sh
# ==============================================================================
# ConfiDoc — Intelligent entrypoint
#
# Both the API and worker services use the same root Dockerfile.
# Set CELERY_WORKER=true on the worker service in Railway to run Celery;
# leave it unset (or set to anything else) to run Uvicorn (API).
# ==============================================================================

set -e

if [ "$CELERY_WORKER" = "true" ]; then
    echo "[entrypoint] CELERY_WORKER=true — starting Celery worker..."
    exec celery -A app.workers.celery_app worker --loglevel=INFO
else
    echo "[entrypoint] Starting Uvicorn API on port ${PORT:-8000}..."
    exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
fi
