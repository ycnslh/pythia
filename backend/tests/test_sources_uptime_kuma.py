from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sources.uptime_kuma import UptimeKumaSource


@pytest.fixture
def source():
    return UptimeKumaSource({"name": "Kuma", "url": "http://kuma:3001", "slug": "default"})


def heartbeat_response(status: int, name: str = "API"):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(
        return_value={"heartbeatList": {"1": [{"status": status, "name": name, "msg": "m"}]}}
    )
    return resp


def patched_client(response=None, error=None):
    client = AsyncMock()
    client.__aenter__.return_value = client
    if error is not None:
        client.get.side_effect = error
    else:
        client.get.return_value = response
    return patch("sources.uptime_kuma.httpx.AsyncClient", return_value=client)


async def fetch_with(source, status):
    with patched_client(heartbeat_response(status)):
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
    with patched_client(error=httpx.ConnectError("refused")):
        with pytest.raises(httpx.ConnectError):
            await source.fetch()
