"""AI Firewall — Redis-backed governance counters.

Best-effort counters surfaced by GET /firewall/stats and the DPO dashboard.
Uses the existing Redis instance (no new infrastructure). Every operation is
fail-open: a Redis outage must never break an AI flow, so recording errors are
swallowed and reads degrade to zeros with ``available: false``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import redis.asyncio as aioredis

from app.config import get_settings
from app.core.logging import get_logger
from app.services.firewall.risk import BLOCK, REDACT, FirewallScan

logger = get_logger("ai_firewall")

_PREFIX = "confidoc:firewall:"
_EVENTS_KEY = _PREFIX + "events"
_EVENTS_MAX = 50

# Stable, ordered list of counters exposed by the stats endpoint.
_COUNTERS: tuple[str, ...] = (
    "prompts_scanned",
    "responses_scanned",
    "redactions",
    "blocks",
    "critical_risks",
)


def _get_redis():
    settings = get_settings()
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)


def _counters_for(scan: FirewallScan) -> list[str]:
    keys: list[str] = []
    if scan.direction == "prompt":
        keys.append("prompts_scanned")
    elif scan.direction == "response":
        keys.append("responses_scanned")
    if scan.verdict == REDACT:
        keys.append("redactions")
    elif scan.verdict == BLOCK:
        keys.append("blocks")
    if scan.risk_level == "critical":
        keys.append("critical_risks")
    return keys


def _event_payload(scan: FirewallScan) -> str:
    """Serialize a leak-safe event: entity types and counts only, never raw PII."""
    return json.dumps(
        {
            "ts": datetime.now(UTC).isoformat(),
            "direction": scan.direction,
            "verdict": scan.verdict,
            "risk_level": scan.risk_level,
            "risk_score": scan.risk_score,
            "findings": [
                {"entity_type": f.entity_type, "severity": f.severity, "count": f.count}
                for f in scan.findings
            ],
        },
        ensure_ascii=False,
    )


async def record_scan(scan: FirewallScan) -> None:
    """Increment counters and append a leak-safe event for a scan. Never raises."""
    keys = _counters_for(scan)
    try:
        client = _get_redis()
        async with client:
            pipe = client.pipeline()
            for key in keys:
                pipe.incr(_PREFIX + key)
            pipe.lpush(_EVENTS_KEY, _event_payload(scan))
            pipe.ltrim(_EVENTS_KEY, 0, _EVENTS_MAX - 1)
            await pipe.execute()
    except Exception as exc:  # noqa: BLE001 — best-effort, must never break AI flow
        logger.warning("firewall_stats_record_failed", error=str(exc))


async def get_recent_events(limit: int = 20) -> list[dict]:
    """Return the most recent firewall events (newest first). Empty on failure."""
    try:
        client = _get_redis()
        async with client:
            raw = await client.lrange(_EVENTS_KEY, 0, max(0, limit - 1))
        return [json.loads(item) for item in raw]
    except Exception as exc:  # noqa: BLE001 — best-effort read
        logger.warning("firewall_events_read_failed", error=str(exc))
        return []


async def get_stats() -> dict:
    """Return the current counters. Degrades to zeros if Redis is unavailable."""
    try:
        client = _get_redis()
        async with client:
            values = await client.mget([_PREFIX + key for key in _COUNTERS])
        counters = {key: int(value or 0) for key, value in zip(_COUNTERS, values, strict=False)}
        return {"available": True, **counters}
    except Exception as exc:  # noqa: BLE001 — best-effort read
        logger.warning("firewall_stats_read_failed", error=str(exc))
        return {"available": False, **{key: 0 for key in _COUNTERS}}
