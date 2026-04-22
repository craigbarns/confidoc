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
    # PDF lourds + OCR + NER : 30 min plafond, soft à 15 min pour signaler avant SIGKILL
    task_time_limit=1800,
    task_soft_time_limit=900,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "ocr": {"exchange": "ocr", "routing_key": "ocr"},
        "nlp": {"exchange": "nlp", "routing_key": "nlp"},
        "io_tasks": {"exchange": "io_tasks", "routing_key": "io_tasks"},
    },
    task_routes={
        "app.workers.tasks.extract_document_task": {"queue": "ocr"},
        "app.workers.tasks.anonymize_document_task": {"queue": "nlp"},
        "app.workers.tasks.process_document_legacy_task": {"queue": "nlp"},
        "app.workers.tasks.run_retention_purge_task": {"queue": "default"},
        "app.workers.tasks.cleanup_stale_celery_results": {"queue": "default"},
    },
)
