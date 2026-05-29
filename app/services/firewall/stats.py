"""AI Firewall — Redis-backed governance counters.

Best-effort counters surfaced by GET /firewall/stats and the DPO dashboard.
Uses the existing Redis instance (no new infrastructure). Every operation is
fail-open: a Redis outage must never break an AI flow, so recording errors are
swallowed and reads degrade to zeros with ``available: false``.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.config import get_settings
from app.core.logging import get_logger
from app.services.firewall.risk import BLOCK, REDACT, FirewallScan

logger = get_logger("ai_firewall")

_PREFIX = "confidoc:firewall:"

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


async def record_scan(scan: FirewallScan) -> None:
    """Increment the relevant counters for a firewall scan. Never raises."""
    keys = _counters_for(scan)
    if not keys:
        return
    try:
        client = _get_redis()
        async with client:
            pipe = client.pipeline()
            for key in keys:
                pipe.incr(_PREFIX + key)
            await pipe.execute()
    except Exception as exc:  # noqa: BLE001 — best-effort, must never break AI flow
        logger.warning("firewall_stats_record_failed", error=str(exc))


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
