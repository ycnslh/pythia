from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sources.rss import RSSSource, MAX_ENTRIES, SEEN_CAP


# ─── Fixtures & helpers ───────────────────────────────────────────────────────


@pytest.fixture
def rss_source():
    return RSSSource({"name": "Test Feed", "url": "https://example.com/feed.xml"})


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


async def test_fetch_handles_network_error_gracefully(rss_source):
    with patch("sources.rss.feedparser.parse", side_effect=Exception("network timeout")):
        events = await rss_source.fetch()

    assert events == []


async def test_fetch_trims_seen_set_when_over_cap(rss_source):
    """_seen should be trimmed when it exceeds SEEN_CAP to bound memory."""
    # Force _seen to be just above the cap
    rss_source._seen = set(str(i) for i in range(SEEN_CAP + 1))
    assert len(rss_source._seen) > SEEN_CAP

    entries = [make_entry("New", link="https://example.com/new", uid="new-uid")]
    with patch("sources.rss.feedparser.parse", return_value=make_feed(entries)):
        await rss_source.fetch()

    assert len(rss_source._seen) < SEEN_CAP
