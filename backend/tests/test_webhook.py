import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sources.webhook import MAX_BODY_BYTES, build_webhook_router


@pytest.fixture
def process():
    return AsyncMock()


@pytest.fixture
def client(process):
    app = FastAPI()
    app.include_router(
        build_webhook_router(
            [{"name": "Alerts", "path": "/webhook/alerts"}, {"name": "NoSlash", "path": "hooks/x"}],
            process_fn=process,
        )
    )
    with TestClient(app) as c:
        yield c


def wait_for(predicate, timeout=2.0):
    import time

    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_accepts_payload_with_202_and_processes_in_background(client, process):
    resp = client.post("/webhook/alerts", json={"title": "Disk full", "message": "98% on /", "url": "https://x"})

    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}
    assert wait_for(lambda: process.await_count == 1)
    event = process.await_args.args[0]
    assert event.title == "Disk full"
    assert event.description == "98% on /"
    assert event.source_name == "Alerts"
    assert event.source_type == "webhook"


def test_responds_before_a_slow_evaluation_finishes(client, process):
    release = asyncio.Event()

    async def slow(_event):
        await release.wait()

    process.side_effect = slow
    resp = client.post("/webhook/alerts", json={"title": "x"})
    assert resp.status_code == 202  # did not wait for the LLM


def test_path_without_leading_slash_is_normalised(client, process):
    assert client.post("/hooks/x", json={"title": "t"}).status_code == 202


def test_title_defaults_when_missing(client, process):
    client.post("/webhook/alerts", json={"text": "only text"})
    assert wait_for(lambda: process.await_count == 1)
    event = process.await_args.args[0]
    assert event.title == "Webhook event"
    assert event.description == "only text"


@pytest.mark.parametrize("body", ["not json", "[1, 2]", '"str"', "42"])
def test_rejects_bodies_that_are_not_a_json_object(client, body):
    resp = client.post("/webhook/alerts", content=body, headers={"content-type": "application/json"})
    assert resp.status_code == 400


def test_rejects_oversized_payload(client):
    big = '{"title": "' + "x" * (MAX_BODY_BYTES + 1) + '"}'
    resp = client.post("/webhook/alerts", content=big, headers={"content-type": "application/json"})
    assert resp.status_code == 413


def test_non_string_fields_do_not_crash(client, process):
    resp = client.post("/webhook/alerts", json={"title": 123, "description": {"a": 1}, "url": ["x"]})
    assert resp.status_code == 202
    assert wait_for(lambda: process.await_count == 1)
    event = process.await_args.args[0]
    assert event.title == "123" and event.url is None


def test_processing_errors_do_not_break_the_server(client, process):
    process.side_effect = RuntimeError("llm exploded")
    assert client.post("/webhook/alerts", json={"title": "a"}).status_code == 202
    assert wait_for(lambda: process.await_count == 1)
    assert client.post("/webhook/alerts", json={"title": "b"}).status_code == 202
