import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import scheduler
from dedupe import TitleDeduplicator
from models import RawEvent
from sources.base import BaseSource
from store import StateStore


class FakeSource(BaseSource):
    """Scripted source: each fetch() pops the next item (list of events, or an exception)."""

    def __init__(self, script, name="Fake", source_type="rss", **config):
        super().__init__({"name": name, "interval": 1, **config})
        self.script = list(script)
        self.type = source_type
        self.state = {"n": 0}

    async def fetch(self):
        item = self.script.pop(0) if self.script else []
        if isinstance(item, Exception):
            raise item
        self.state["n"] += 1
        return item

    def export_state(self):
        return dict(self.state)

    def load_state(self, state):
        self.state = dict(state)


def raw(title, source_type="rss", source="Fake"):
    return RawEvent(title=title, source_name=source, source_type=source_type)


class _Stop(BaseException):
    """Raised by the fake sleep to end the endless polling loop."""


async def run_polls(source, polls, store=None, dedupe=None):
    """Run the poller until `polls` fetches happened, without real sleeping.

    Returns the list of delays the scheduler asked to sleep.
    """
    calls = 0
    real_fetch = source.fetch

    async def counting_fetch():
        nonlocal calls
        calls += 1
        return await real_fetch()

    source.fetch = counting_fetch
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay):
        sleeps.append(delay)
        if calls >= polls:
            raise _Stop
        await real_sleep(0)

    with patch("scheduler.asyncio.sleep", fake_sleep):
        try:
            await scheduler._poll_source(source, store, dedupe)
        except _Stop:
            pass
    return sleeps


@pytest.fixture
def process():
    with patch("scheduler.process_event", new=AsyncMock()) as mock:
        yield mock


async def test_events_are_processed_and_source_marked_healthy(process):
    src = FakeSource([[raw("one"), raw("two")]])
    await run_polls(src, 1)

    assert [c.args[0].title for c in process.call_args_list] == ["one", "two"]
    assert scheduler.source_health["Fake"] is True


async def test_failure_marks_unhealthy_and_backs_off_exponentially(process):
    src = FakeSource([RuntimeError("boom"), RuntimeError("boom"), []], name="Flaky")
    sleeps = await run_polls(src, 3)

    assert sleeps[:2] == [2, 4]  # interval * 2**n
    assert scheduler.source_health["Flaky"] is True  # recovered on the 3rd poll


async def test_backoff_is_capped(process):
    src = FakeSource([RuntimeError("boom")] * 30, name="Dead", max_failures=0)
    sleeps = await run_polls(src, 30)

    assert max(sleeps) == scheduler.MAX_BACKOFF_S
    assert scheduler.source_health["Dead"] is False


async def test_source_is_disabled_after_max_consecutive_failures(process, caplog):
    src = FakeSource([RuntimeError("boom")] * 10, name="Gone", max_failures=3)
    with caplog.at_level("WARNING", logger="scheduler"):
        sleeps = await run_polls(src, 10)

    assert len(src.script) == 7  # only 3 of the 10 scripted fetches ran
    assert len(sleeps) == 2  # the 3rd failure returns instead of sleeping
    assert scheduler.source_health["Gone"] is False
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert "disabled until restart" in errors[0].getMessage()
    process.assert_not_called()


async def test_default_cap_applies_when_unconfigured(process):
    src = FakeSource([RuntimeError("boom")] * 30, name="DeadDefault")
    sleeps = await run_polls(src, 30)

    assert len(sleeps) == scheduler.DEFAULT_MAX_FAILURES - 1
    assert len(src.script) == 30 - scheduler.DEFAULT_MAX_FAILURES


async def test_success_resets_the_failure_count(process):
    # 2 failures, a success, 2 more failures: never 3 in a row, so never disabled.
    script = [RuntimeError("x"), RuntimeError("x"), [], RuntimeError("x"), RuntimeError("x"), []]
    src = FakeSource(script, name="Recovers", max_failures=3)
    await run_polls(src, 6)

    assert src.script == []
    assert scheduler.source_health["Recovers"] is True


async def test_duplicate_rss_headlines_are_evaluated_once(process):
    src = FakeSource([[raw("Earthquake strikes northern Japan today"),
                       raw("Earthquake strikes northern Japan today")]])
    await run_polls(src, 1, dedupe=TitleDeduplicator())

    assert process.call_count == 1


async def test_repeated_monitoring_events_are_never_deduplicated(process):
    events = [raw("API is DOWN", source_type="uptime_kuma"),
              raw("API is DOWN", source_type="uptime_kuma")]
    await run_polls(FakeSource([events]), 1, dedupe=TitleDeduplicator())

    assert process.call_count == 2


async def test_state_is_persisted_and_restored(process, tmp_path):
    store = StateStore(str(tmp_path))
    await run_polls(FakeSource([[], []], name="Persist"), 2, store=store)

    restored = FakeSource([[]], name="Persist")
    await run_polls(restored, 1, store=store)
    assert restored.state["n"] == 3  # picked up the 2 fetches of the previous run


async def test_state_is_saved_before_evaluation(tmp_path):
    """A crash during evaluation must not make the same items be fetched again."""
    store = StateStore(str(tmp_path))
    saved_before_eval = []

    async def exploding_process(event):
        saved_before_eval.append(store.load(scheduler.state_key("source", "Crash")))
        raise asyncio.CancelledError  # simulates the task being killed mid-evaluation

    src = FakeSource([[raw("x")]], name="Crash")
    with patch("scheduler.process_event", exploding_process):
        await scheduler._poll_source(src, store)

    assert saved_before_eval == [{"n": 1}]
