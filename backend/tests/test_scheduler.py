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

    def __init__(self, script, name="Fake", source_type="rss"):
        super().__init__({"name": name, "interval": 1})
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
    src = FakeSource([RuntimeError("boom")] * 30, name="Dead")
    sleeps = await run_polls(src, 30)

    assert max(sleeps) == scheduler.MAX_BACKOFF_S
    assert scheduler.source_health["Dead"] is False


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
