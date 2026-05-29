"""Unit tests for the AI Firewall Redis-backed counters."""

import pytest

from app.services.firewall import stats as fw_stats
from app.services.firewall.risk import FirewallScan


class _FakePipe:
    def __init__(self, store: dict) -> None:
        self._store = store
        self._ops: list[str] = []

    def incr(self, key: str) -> "_FakePipe":
        self._ops.append(key)
        return self

    async def execute(self) -> list[int]:
        for key in self._ops:
            self._store[key] = self._store.get(key, 0) + 1
        return [self._store[k] for k in self._ops]


class _FakeRedis:
    def __init__(self, store: dict) -> None:
        self._store = store

    async def __aenter__(self) -> "_FakeRedis":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def pipeline(self) -> _FakePipe:
        return _FakePipe(self._store)

    async def mget(self, keys: list[str]) -> list:
        return [self._store.get(k) for k in keys]


@pytest.fixture
def fake_redis(monkeypatch):
    store: dict[str, int] = {}
    monkeypatch.setattr(fw_stats, "_get_redis", lambda: _FakeRedis(store))
    return store


async def test_record_prompt_allow_increments_only_prompts_scanned(fake_redis):
    await fw_stats.record_scan(FirewallScan(direction="prompt", verdict="allow", risk_level="low"))
    assert fake_redis[fw_stats._PREFIX + "prompts_scanned"] == 1
    assert "redactions" not in {k.split(":")[-1] for k in fake_redis}


async def test_record_prompt_redact_increments_prompts_and_redactions(fake_redis):
    await fw_stats.record_scan(
        FirewallScan(direction="prompt", verdict="redact", risk_level="high")
    )
    assert fake_redis[fw_stats._PREFIX + "prompts_scanned"] == 1
    assert fake_redis[fw_stats._PREFIX + "redactions"] == 1


async def test_record_response_block_critical_increments_all_relevant(fake_redis):
    await fw_stats.record_scan(
        FirewallScan(direction="response", verdict="block", risk_level="critical")
    )
    assert fake_redis[fw_stats._PREFIX + "responses_scanned"] == 1
    assert fake_redis[fw_stats._PREFIX + "blocks"] == 1
    assert fake_redis[fw_stats._PREFIX + "critical_risks"] == 1


async def test_get_stats_reflects_recorded_counters(fake_redis):
    await fw_stats.record_scan(FirewallScan(direction="prompt", verdict="allow", risk_level="low"))
    await fw_stats.record_scan(
        FirewallScan(direction="response", verdict="redact", risk_level="medium")
    )

    stats = await fw_stats.get_stats()
    assert stats["available"] is True
    assert stats["prompts_scanned"] == 1
    assert stats["responses_scanned"] == 1
    assert stats["redactions"] == 1
    assert stats["blocks"] == 0


async def test_record_scan_never_raises_when_redis_unavailable(monkeypatch):
    def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(fw_stats, "_get_redis", _boom)
    # Must not raise — stats are best-effort and must never break the AI flow.
    await fw_stats.record_scan(
        FirewallScan(direction="prompt", verdict="block", risk_level="critical")
    )


async def test_get_stats_degrades_gracefully_when_redis_unavailable(monkeypatch):
    def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(fw_stats, "_get_redis", _boom)
    stats = await fw_stats.get_stats()
    assert stats["available"] is False
    assert stats["prompts_scanned"] == 0
