"""ConfiDoc Backend — Prometheus Metrics."""

import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# ── Counters ──────────────────────────────────────────────────────────
DOCUMENT_UPLOADS = Counter(
    "confidoc_document_uploads_total",
    "Total number of document uploads",
    ["extension"]
)

PIPELINE_STEPS = Counter(
    "confidoc_pipeline_steps_total",
    "Total number of pipeline steps executed",
    ["step", "status"]
)

LLM_CALLS = Counter(
    "confidoc_llm_calls_total",
    "Total number of LLM calls",
    ["provider", "model", "status"]
)

# ── Histograms ───────────────────────────────────────────────────────
PIPELINE_LATENCY = Histogram(
    "confidoc_pipeline_step_duration_seconds",
    "Latency of pipeline steps in seconds",
    ["step"]
)

OCR_LATENCY = Histogram(
    "confidoc_ocr_duration_seconds",
    "Latency of OCR extraction in seconds",
    ["engine"]
)

LLM_LATENCY = Histogram(
    "confidoc_llm_duration_seconds",
    "Latency of LLM calls in seconds",
    ["provider", "model"]
)

# ── Gauges ───────────────────────────────────────────────────────────
ACTIVE_TASKS = Gauge(
    "confidoc_active_background_tasks",
    "Number of currently active Celery tasks",
    ["queue"]
)


def get_metrics_response() -> Response:
    """FastAPI compatible metrics response."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
