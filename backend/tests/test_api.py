import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import main
from event_queue import queue


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


# ─── API ──────────────────────────────────────────────────────────────────────


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm"] is None  # no evaluation yet


def test_events_endpoint_returns_history(client, evaluated_event):
    import asyncio

    asyncio.run(queue.publish(evaluated_event))
    assert client.get("/api/events").json()["events"][0]["title"] == evaluated_event.title


def test_system_endpoint_reports_sources_and_llm(client):
    body = client.get("/api/system").json()
    assert body["llm"]["model"] == "test-model"
    assert body["llm"]["healthy"] is None
    assert "cpu" in body and "ram_pct" in body
    assert body["sources"] == []  # the only configured source is a webhook


def test_llm_health_is_exposed_after_a_failure(client):
    from evaluator import llm_health

    llm_health.update(ok=False)
    assert client.get("/api/system").json()["llm"]["healthy"] is False
    assert client.get("/health").json()["llm"] is False


def test_provider_names():
    assert main._llm_provider("https://openrouter.ai/api/v1") == "OpenRouter"
    assert main._llm_provider("http://localhost:11434/v1") == "Local"
    assert main._llm_provider("https://llm.example.org/v1") == "llm.example.org"


# ─── WebSocket ────────────────────────────────────────────────────────────────


def test_websocket_sends_history_then_live_events(client, evaluated_event):
    import asyncio

    asyncio.run(queue.publish(evaluated_event))
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["type"] == "history" and len(first["events"]) == 1

        # a live event published later arrives as an "event" frame
        with patch("pipeline.evaluate", AsyncMock(return_value=evaluated_event)):
            client.post("/webhook/alerts", json={"title": "live"})
            frame = ws.receive_json()
        assert frame["type"] == "event"
        assert frame["event"]["title"] == evaluated_event.title

    deadline = time.time() + 2
    while queue.connection_count and time.time() < deadline:
        time.sleep(0.01)
    assert queue.connection_count == 0  # disconnect cleaned up


# ─── Webhook through the real app ─────────────────────────────────────────────


def test_webhook_registered_from_sources_file_is_not_shadowed_by_spa(client, evaluated_event):
    with patch("pipeline.evaluate", AsyncMock(return_value=evaluated_event)):
        resp = client.post("/webhook/alerts", json={"title": "hello"})
        assert resp.status_code == 202
        deadline = time.time() + 2
        while not queue.history and time.time() < deadline:
            time.sleep(0.01)
    assert queue.history


# ─── Frontend serving ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/", "/display", "/feed", "/anything/else"])
def test_spa_routes_serve_index_with_injected_config(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert "window.__PYTHIA__=" in resp.text
    assert '"language": "en"' in resp.text
    assert '"displayThreshold": 4.0' in resp.text
    assert resp.headers["cache-control"] == "no-cache"


def test_assets_and_root_files_are_served(client):
    assert client.get("/assets/app.js").text == "console.log('app')"
    assert client.get("/favicon.svg").text == "<svg/>"


def test_unknown_api_path_is_404_not_the_spa(client):
    assert client.get("/api/nope").status_code == 404
    assert client.get("/webhook/unknown").status_code in (404, 405)


def test_path_traversal_cannot_escape_the_static_dir(client):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt"):
        resp = client.get(path)
        assert "top secret" not in resp.text


def test_injected_config_cannot_break_out_of_the_script_tag():
    from static import render_index

    with patch("static.runtime_config", return_value={"language": "</script><b>"}):
        html = render_index("<html><head></head></html>")
    assert "</script><b>" not in html


def test_shutdown_stops_pollers_then_closes_their_http_clients():
    import asyncio

    order = []
    cfg = {"type": "rss", "name": "Feed", "url": "http://localhost/feed.xml", "interval": 300}

    def fake_start(sources, store, dedupe):
        async def poll():
            try:
                await asyncio.sleep(3600)
            finally:
                order.append("poller stopped")

        return [asyncio.create_task(poll())]

    async def fake_aclose(self):
        order.append("client closed")

    with (
        patch("main.load_sources", return_value=[cfg]),
        patch("main.start_scheduler", fake_start),
        patch("sources.base.BaseSource.aclose", fake_aclose),
        TestClient(main.app),
    ):
        pass

    assert order == ["poller stopped", "client closed"]
