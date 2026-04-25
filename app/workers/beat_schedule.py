"""ConfiDoc Backend — Celery Beat configuration.

Ce fichier configure les tâches planifiées (cron).
À utiliser comme point d'entrée pour le service Celery Beat sur Railway :

    celery -A app.workers.beat_schedule beat -l info

Ou avec le scheduler persistant (évite les tâches dupliquées si redémarrage) :

    celery -A app.workers.beat_schedule beat -l info -S redbeat.RedBeatScheduler
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings
from app.workers.celery_app import celery_app  # Réutilise la config existante

settings = get_settings()

# Hérite de la config du worker principal + ajoute le beat schedule
celery_app.conf.update(
    beat_schedule={
        "retention-purge-daily": {
            "task": "app.workers.tasks.run_retention_purge_task",
            "schedule": crontab(hour=2, minute=0),  # 02:00 UTC
            "options": {"queue": "celery"},
        },
        "cleanup-celery-results-weekly": {
            "task": "app.workers.tasks.cleanup_stale_celery_results",
            "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),  # Dim 03:00 UTC
            "options": {"queue": "celery"},
        },
    },
    timezone="Europe/Paris",
    enable_utc=True,
)
