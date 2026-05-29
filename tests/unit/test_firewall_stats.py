"""Unit tests for the AI Firewall Redis-backed counters."""

import pytest

from app.services.firewall import stats as fw_stats
from app.services.firewall.risk import FirewallScan


class _FakePipe:
    def __init__(self, store: dict, lists: dict) -> None:
        self._store = store
        self._lists = lists
        self._ops: list = []

    def incr(self, key: str) -> "_FakePipe":
        self._ops.append(("incr", key))
        return self

    def lpush(self, key: str, value: str) -> "_FakePipe":
        self._ops.append(("lpush", key, value))
        return self

    def ltrim(self, key: str, start: int, end: int) -> "_FakePipe":
        self._ops.append(("ltrim", key, start, end))
        return self

    async def execute(self) -> list:
        results: list = []
        for op in self._ops:
            if op[0] == "incr":
                self._store[op[1]] = self._store.get(op[1], 0) + 1
                results.append(self._store[op[1]])
            elif op[0] == "lpush":
                self._lists.setdefault(op[1], []).insert(0, op[2])
                results.append(len(self._lists[op[1]]))
            elif op[0] == "ltrim":
                self._lists[op[1]] = self._lists[op[1]][op[2] : op[3] + 1]
                results.append(True)
        return results


class _FakeRedis:
    def __init__(self, store: dict, lists: dict) -> None:
        self._store = store
        self._lists = lists

    async def __aenter__(self) -> "_FakeRedis":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def pipeline(self) -> _FakePipe:
        return _FakePipe(self._store, self._lists)

    async def mget(self, keys: list[str]) -> list:
        return [self._store.get(k) for k in keys]

    async def lrange(self, key: str, start: int, end: int) -> list:
        return self._lists.get(key, [])[start : end + 1]


class _Backing:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.lists: dict[str, list] = {}


@pytest.fixture
def fake_redis(monkeypatch):
    backing = _Backing()
    monkeypatch.setattr(fw_stats, "_get_redis", lambda: _FakeRedis(backing.store, backing.lists))
    return backing


async def test_record_prompt_allow_increments_only_prompts_scanned(fake_redis):
    await fw_stats.record_scan(FirewallScan(direction="prompt", verdict="allow", risk_level="low"))
    assert fake_redis.store[fw_stats._PREFIX + "prompts_scanned"] == 1
    assert fw_stats._PREFIX + "redactions" not in fake_redis.store


async def test_record_prompt_redact_increments_prompts_and_redactions(fake_redis):
    await fw_stats.record_scan(
        FirewallScan(direction="prompt", verdict="redact", risk_level="high")
    )
    assert fake_redis.store[fw_stats._PREFIX + "prompts_scanned"] == 1
    assert fake_redis.store[fw_stats._PREFIX + "redactions"] == 1


async def test_record_response_block_critical_increments_all_relevant(fake_redis):
    await fw_stats.record_scan(
        FirewallScan(direction="response", verdict="block", risk_level="critical")
    )
    assert fake_redis.store[fw_stats._PREFIX + "responses_scanned"] == 1
    assert fake_redis.store[fw_stats._PREFIX + "blocks"] == 1
    assert fake_redis.store[fw_stats._PREFIX + "critical_risks"] == 1


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


async def test_record_scan_appends_leak_safe_event(fake_redis):
    from app.services.firewall.risk import FirewallFinding

    await fw_stats.record_scan(
        FirewallScan(
            direction="response",
            verdict="block",
            risk_level="critical",
            findings=[FirewallFinding("IBAN", "critical", 1, "[IBAN]")],
        )
    )
    events = await fw_stats.get_recent_events()
    assert len(events) == 1
    evt = events[0]
    assert evt["direction"] == "response"
    assert evt["verdict"] == "block"
    assert evt["findings"][0]["entity_type"] == "IBAN"
    # The event must never carry a raw PII value.
    assert "FR76" not in str(evt)


async def test_recent_events_are_capped_and_newest_first(fake_redis):
    for i in range(fw_stats._EVENTS_MAX + 5):
        verdict = "redact" if i % 2 else "allow"
        await fw_stats.record_scan(
            FirewallScan(direction="prompt", verdict=verdict, risk_level="low")
        )
    all_events = await fw_stats.get_recent_events(limit=100)
    assert len(all_events) == fw_stats._EVENTS_MAX  # capped


async def test_get_recent_events_empty_when_redis_unavailable(monkeypatch):
    def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(fw_stats, "_get_redis", _boom)
    assert await fw_stats.get_recent_events() == []


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
