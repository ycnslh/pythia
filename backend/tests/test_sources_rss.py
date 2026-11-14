from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
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


# ─── Shared client & conditional GET ──────────────────────────────────────────


def feed_xml(*titles):
    items = "".join(
        f"<item><title>{t}</title><link>https://example.com/{i}</link><guid>g{i}</guid></item>"
        for i, t in enumerate(titles)
    )
    return f"<rss version='2.0'><channel><title>T</title>{items}</channel></rss>".encode()


def serve(source, handler):
    """Route the source's HTTP client to `handler` (no real network)."""
    requests = []

    def recording(request):
        requests.append(request)
        return handler(request)

    source._client = httpx.AsyncClient(transport=httpx.MockTransport(recording))
    return requests


def etag_server(body, etag='"v1"', last_modified="Sat, 14 Nov 2026 10:00:00 GMT"):
    def handler(request):
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304)
        return httpx.Response(
            200, content=body, headers={"ETag": etag, "Last-Modified": last_modified}
        )

    return handler


async def test_304_means_no_change_without_error_or_event():
    source = RSSSource({"name": "Cond", "url": "https://example.com/feed.xml"})
    requests = serve(source, etag_server(feed_xml("a", "b")))

    assert len(await source.fetch()) == 2  # first poll: 200
    assert "if-none-match" not in requests[0].headers

    with patch("sources.rss.feedparser.parse") as parse:
        assert await source.fetch() == []  # second poll: 304
        parse.assert_not_called()  # nothing downloaded, nothing parsed

    assert requests[1].headers["if-none-match"] == '"v1"'
    assert requests[1].headers["if-modified-since"] == "Sat, 14 Nov 2026 10:00:00 GMT"
    assert source.export_state()["etag"] == '"v1"'


async def test_changed_feed_after_validators_emits_new_entries():
    source = RSSSource({"name": "Cond", "url": "https://example.com/feed.xml"})
    serve(source, etag_server(feed_xml("a")))
    await source.fetch()

    serve(source, etag_server(feed_xml("a", "b"), etag='"v2"'))  # validator no longer matches
    events = await source.fetch()
    assert [e.title for e in events] == ["b"]
    assert source._etag == '"v2"'


async def test_validators_survive_a_restart():
    source = RSSSource({"name": "Cond", "url": "https://example.com/feed.xml"})
    serve(source, etag_server(feed_xml("a")))
    await source.fetch()
    state = source.export_state()

    restarted = RSSSource({"name": "Cond", "url": "https://example.com/feed.xml"})
    restarted.load_state(state)
    requests = serve(restarted, etag_server(feed_xml("a")))
    assert await restarted.fetch() == []
    assert requests[0].headers["if-none-match"] == '"v1"'
    assert requests[0].method == "GET"


async def test_no_validators_are_sent_before_the_first_successful_poll():
    source = RSSSource({"name": "Cond", "url": "https://example.com/feed.xml"})
    source.load_state({"seen": [], "etag": '"v1"', "last_modified": "x"})
    requests = serve(source, etag_server(feed_xml("a")))

    assert len(await source.fetch()) == 1  # not a 304: backlog baseline still applies
    assert "if-none-match" not in requests[0].headers


async def test_backlog_beyond_the_cap_forces_a_full_download_next_time():
    titles = [f"t{i}" for i in range(MAX_ENTRIES + 3)]
    source = RSSSource({"name": "Cond", "url": "https://example.com/feed.xml"})
    source._primed = True  # not the baseline poll: the extra entries are a real backlog
    requests = serve(source, etag_server(feed_xml(*titles)))

    assert len(await source.fetch()) == MAX_ENTRIES
    assert source._etag is None  # a 304 would hide the 3 entries left

    assert len(await source.fetch()) == 3  # downloaded again, not 304
    assert "if-none-match" not in requests[1].headers
    assert source._etag == '"v1"'


async def test_unparseable_response_does_not_store_validators():
    source = RSSSource({"name": "Cond", "url": "https://example.com/feed.xml"})
    serve(source, lambda r: httpx.Response(200, content=b"not a feed", headers={"ETag": '"bad"'}))

    with pytest.raises(ValueError):
        await source.fetch()
    assert source._etag is None


async def test_http_error_propagates():
    source = RSSSource({"name": "Cond", "url": "https://example.com/feed.xml"})
    serve(source, lambda r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await source.fetch()


async def test_client_is_reused_across_polls_and_closed_once():
    source = RSSSource({"name": "Cond", "url": "https://example.com/feed.xml"})
    client = source.client
    assert source.client is client
    assert client.headers["user-agent"].startswith("PYTHIA")
    assert client.follow_redirects is True
    await source.aclose()
    assert client.is_closed
