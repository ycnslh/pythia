import httpx
import pytest

from sources.uptime_kuma import UptimeKumaSource


@pytest.fixture
def source():
    return UptimeKumaSource({"name": "Kuma", "url": "http://kuma:3001", "slug": "default"})


def heartbeat_json(status: int, name: str = "API") -> dict:
    return {"heartbeatList": {"1": [{"status": status, "name": name, "msg": "m"}]}}


def use_handler(source, handler):
    """Route the source's HTTP client to `handler` (no real network)."""
    source._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def fetch_with(source, status):
    use_handler(source, lambda request: httpx.Response(200, json=heartbeat_json(status)))
    return await source.fetch()


async def test_first_poll_sets_baseline_without_event(source):
    assert await fetch_with(source, 1) == []


async def test_emits_event_on_down_transition(source):
    await fetch_with(source, 1)
    events = await fetch_with(source, 0)

    assert len(events) == 1
    assert events[0].title == "API is DOWN"


async def test_pending_status_is_not_reported_as_down(source):
    await fetch_with(source, 1)

    assert await fetch_with(source, 2) == []  # pending
    assert await fetch_with(source, 3) == []  # maintenance
    # Back to up: no transition, because the last definitive state was already up
    assert await fetch_with(source, 1) == []


async def test_network_error_propagates_for_scheduler(source):
    def refuse(request):
        raise httpx.ConnectError("refused")

    use_handler(source, refuse)
    with pytest.raises(httpx.ConnectError):
        await source.fetch()


async def test_known_state_survives_a_restart(source):
    await fetch_with(source, 1)
    state = source.export_state()

    restarted = UptimeKumaSource({"name": "Kuma", "url": "http://kuma:3001"})
    restarted.load_state(state)
    # Went down while PYTHIA was off: the transition is reported right after restart
    events = await fetch_with(restarted, 0)
    assert [e.title for e in events] == ["API is DOWN"]


def test_load_state_ignores_garbage():
    source = UptimeKumaSource({"name": "Kuma", "url": "http://kuma:3001"})
    source.load_state({"last_states": "nope"})
    assert source.export_state() == {"last_states": {}}


async def test_http_error_propagates_for_scheduler(source):
    use_handler(source, lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await source.fetch()


async def test_client_is_created_once_and_reused(source):
    assert source._client is None  # nothing opened until the first poll
    assert source.client is source.client


async def test_conditional_get_and_304_means_no_change(source):
    seen_headers = []

    def handler(request):
        seen_headers.append(dict(request.headers))
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, json=heartbeat_json(1), headers={"ETag": '"v1"'})

    use_handler(source, handler)
    assert await source.fetch() == []  # baseline
    assert "if-none-match" not in seen_headers[0]

    assert await source.fetch() == []  # 304: no error, no event
    assert seen_headers[1]["if-none-match"] == '"v1"'
    assert source.export_state() == {"last_states": {"1": 1}}


async def test_aclose_closes_the_client(source):
    client = source.client
    await source.aclose()
    assert client.is_closed
    assert source._client is None
    await source.aclose()  # idempotent
