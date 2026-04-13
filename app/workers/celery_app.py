"""ConfiDoc Backend — Celery application configuration."""

from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "confidoc",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    worker_prefetch_multiplier=1,
    task_default_queue="celery",
)
