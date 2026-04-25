"""Tests for Celery dispatch probes."""


class _InspectStub:
    def __init__(self, queues_by_worker):
        self.queues_by_worker = queues_by_worker

    def ping(self):
        return {name: {"ok": "pong"} for name in self.queues_by_worker}

    def active_queues(self):
        return {
            name: [{"name": queue_name} for queue_name in queues]
            for name, queues in self.queues_by_worker.items()
        }


def test_celery_workers_available_requires_requested_queue(monkeypatch):
    from app.workers.celery_app import celery_app
    from app.workers.tasks import celery_workers_available

    monkeypatch.setattr(
        celery_app.control,
        "inspect",
        lambda timeout=1.0: _InspectStub({"worker-a": ["default", "ocr"]}),
    )

    assert celery_workers_available(queue="ocr") is True
    assert celery_workers_available(queue="nlp") is False


def test_celery_workers_available_without_queue_accepts_ping(monkeypatch):
    from app.workers.celery_app import celery_app
    from app.workers.tasks import celery_workers_available

    monkeypatch.setattr(
        celery_app.control,
        "inspect",
        lambda timeout=1.0: _InspectStub({"worker-a": ["default"]}),
    )

    assert celery_workers_available() is True


def test_document_tasks_use_api_background_by_default(monkeypatch):
    from app.config import get_settings
    from app.workers.tasks import should_dispatch_document_task_to_celery

    get_settings.cache_clear()
    monkeypatch.delenv("DOCUMENT_PROCESSING_BACKEND", raising=False)
    try:
        assert should_dispatch_document_task_to_celery(queue="nlp") is False
    finally:
        get_settings.cache_clear()


def test_document_tasks_require_celery_backend_and_queue(monkeypatch):
    from app.config import get_settings
    from app.workers.celery_app import celery_app
    from app.workers.tasks import should_dispatch_document_task_to_celery

    monkeypatch.setenv("DOCUMENT_PROCESSING_BACKEND", "celery")
    get_settings.cache_clear()
    monkeypatch.setattr(
        celery_app.control,
        "inspect",
        lambda timeout=1.0: _InspectStub({"worker-a": ["default", "nlp"]}),
    )

    try:
        assert should_dispatch_document_task_to_celery(queue="nlp") is True
        assert should_dispatch_document_task_to_celery(queue="ocr") is False
    finally:
        get_settings.cache_clear()
