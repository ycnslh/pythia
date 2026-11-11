from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from sources.rss import MAX_ENTRIES, SEEN_CAP, RSSSource

# ─── Fixtures & helpers ───────────────────────────────────────────────────────


@pytest.fixture
def rss_source():
    source = RSSSource({"name": "Test Feed", "url": "https://example.com/feed.xml"})
    # No real network in tests: the downloaded payload is irrelevant because
    # feedparser.parse is patched in each test.
    source._download = AsyncMock(return_value=b"<rss/>")
    return source


def make_entry(title="Test Entry", link="https://example.com/1", uid=None, summary="Test summary"):
    """Build a feedparser-style entry object."""
    data = {
        "title": title,
        "link": link,
        "id": uid,
        "summary": summary,
        "description": None,
    }
    entry = SimpleNamespace(**{k: v for k, v in data.items()})
    # feedparser entries also support .get()
    entry.get = lambda key, default=None: data.get(key) if data.get(key) is not None else default
    return entry


def make_feed(entries, feed_title="Test Feed Title"):
    feed = SimpleNamespace(
        entries=entries,
        feed=SimpleNamespace(title=feed_title, get=lambda key, default="": getattr(SimpleNamespace(title=feed_title), key, default)),
        get=lambda key, default=None: default,  # like FeedParserDict.get (no bozo flag)
    )
    return feed


# ─── fetch() ─────────────────────────────────────────────────────────────────


async def test_fetch_returns_raw_events(rss_source):
    entries = [
        make_entry(f"Entry {i}", link=f"https://example.com/{i}", uid=f"uid-{i}")
        for i in range(3)
    ]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        events = await rss_source.fetch()

    assert len(events) == 3
    assert all(e.source_name == "Test Feed" for e in events)
    assert all(e.source_type == "rss" for e in events)


async def test_fetch_caps_at_max_entries(rss_source):
    entries = [
        make_entry(f"Entry {i}", uid=f"uid-{i}") for i in range(MAX_ENTRIES + 5)
    ]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        events = await rss_source.fetch()

    assert len(events) == MAX_ENTRIES


async def test_fetch_deduplicates_by_uid(rss_source):
    entries = [make_entry("Entry", link="https://example.com/1", uid="uid-1")]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        first = await rss_source.fetch()
        second = await rss_source.fetch()

    assert len(first) == 1
    assert len(second) == 0  # already seen


async def test_fetch_deduplicates_by_link_when_no_id(rss_source):
    entries = [make_entry("Entry", link="https://example.com/unique", uid=None)]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        first = await rss_source.fetch()
        second = await rss_source.fetch()

    assert len(first) == 1
    assert len(second) == 0


async def test_fetch_maps_fields_correctly(rss_source):
    entries = [make_entry("My Title", link="https://example.com/x", uid="id-x", summary="My summary")]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        events = await rss_source.fetch()

    assert events[0].title == "My Title"
    assert events[0].url == "https://example.com/x"
    assert events[0].description == "My summary"


async def test_fetch_propagates_network_errors(rss_source):
    """Errors must reach the scheduler so it can flag the source and back off."""
    rss_source._download = AsyncMock(side_effect=RuntimeError("network timeout"))

    with pytest.raises(RuntimeError, match="network timeout"):
        await rss_source.fetch()


async def test_fetch_raises_on_unparseable_feed(rss_source):
    feed = make_feed([])
    feed.get = lambda key, default=None: {"bozo": True, "bozo_exception": "not xml"}.get(key, default)
    with patch("sources.rss.feedparser.parse", return_value=feed):
        with pytest.raises(ValueError, match="Unparseable feed"):
            await rss_source.fetch()


async def test_fetch_tolerates_bozo_feed_with_entries(rss_source):
    """Minor XML defects (bozo) are fine as long as entries were recovered."""
    feed = make_feed([make_entry("Entry", uid="uid-1")])
    feed.get = lambda key, default=None: {"bozo": True}.get(key, default)
    with patch("sources.rss.feedparser.parse", return_value=feed):
        events = await rss_source.fetch()

    assert len(events) == 1


async def test_fetch_trims_seen_set_when_over_cap(rss_source):
    """_seen should be trimmed when it exceeds SEEN_CAP to bound memory."""
    # Force _seen to be just above the cap
    from collections import OrderedDict
    rss_source._seen = OrderedDict((str(i), None) for i in range(SEEN_CAP + 1))
    assert len(rss_source._seen) > SEEN_CAP

    entries = [make_entry("New", link="https://example.com/new", uid="new-uid")]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        await rss_source.fetch()

    assert len(rss_source._seen) < SEEN_CAP


# ─── Persisted state ──────────────────────────────────────────────────────────


async def test_seen_ids_survive_a_restart(rss_source):
    entries = [make_entry("Entry", link="https://example.com/1", uid="uid-1")]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        assert len(await rss_source.fetch()) == 1
        state = rss_source.export_state()

        restarted = RSSSource({"name": "Test Feed", "url": "https://example.com/feed.xml"})
        restarted._download = AsyncMock(return_value=b"<rss/>")
        restarted.load_state(state)
        assert await restarted.fetch() == []  # already seen: not evaluated again


def test_load_state_ignores_garbage():
    source = RSSSource({"name": "x", "url": "u"})
    source.load_state({"seen": "not a list"})
    source.load_state({})
    assert len(source._seen) == 0


def test_load_state_caps_size():
    source = RSSSource({"name": "x", "url": "u"})
    source.load_state({"seen": [str(i) for i in range(SEEN_CAP + 500)]})
    assert len(source._seen) == SEEN_CAP


# ─── First-poll baseline ──────────────────────────────────────────────────────


async def test_first_poll_swallows_the_older_backlog(rss_source):
    entries = [make_entry(f"Entry {i}", uid=f"uid-{i}") for i in range(MAX_ENTRIES + 8)]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        first = await rss_source.fetch()
        second = await rss_source.fetch()

    assert len(first) == MAX_ENTRIES
    assert second == []  # the 8 older items were marked seen, not queued for later


async def test_later_bursts_are_still_spread_over_polls(rss_source):
    with patch("sources.rss.feedparser.parse", return_value=make_feed([make_entry("old", uid="old")])):
        await rss_source.fetch()  # baseline poll

    burst = [make_entry(f"New {i}", uid=f"new-{i}") for i in range(MAX_ENTRIES + 3)]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(burst)):
        first = await rss_source.fetch()
        second = await rss_source.fetch()

    assert len(first) == MAX_ENTRIES
    assert len(second) == 3  # the rest follows on the next poll


async def test_restored_state_counts_as_already_primed():
    source = RSSSource({"name": "x", "url": "u"})
    source._download = AsyncMock(return_value=b"")
    source.load_state({"seen": ["seen-1"]})
    entries = [make_entry(f"E{i}", uid=f"u{i}") for i in range(MAX_ENTRIES + 3)]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        first = await source.fetch()
        second = await source.fetch()

    assert len(first) == MAX_ENTRIES and len(second) == 3
