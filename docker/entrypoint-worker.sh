#!/bin/sh
# ==============================================================================
# ConfiDoc — Celery Worker Entrypoint
# This script is the ONLY entrypoint for the worker container.
# It explicitly refuses to start Uvicorn/FastAPI.
# ==============================================================================
set -e

echo "[entrypoint-worker] Starting Celery worker..."
echo "[entrypoint-worker] Broker: ${CELERY_BROKER_URL:-<not set>}"

# Safety guard: abort if someone tries to inject a uvicorn command
if echo "$@" | grep -qi "uvicorn"; then
    echo "[entrypoint-worker] ERROR: uvicorn is not allowed in the worker container. Aborting." >&2
    exit 1
fi

exec celery -A app.workers.celery_app worker --loglevel=INFO "$@"
