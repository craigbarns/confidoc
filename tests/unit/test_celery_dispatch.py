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
