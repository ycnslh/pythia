from unittest.mock import AsyncMock, MagicMock

import pytest

from event_queue import HISTORY_MAXLEN, EventQueue


@pytest.fixture
def queue():
    return EventQueue()


# ─── publish ──────────────────────────────────────────────────────────────────


async def test_publish_adds_event_to_history(queue, evaluated_event):
    assert len(queue.history) == 0
    await queue.publish(evaluated_event)
    assert len(queue.history) == 1
    assert queue.history[0]["criticality"] == evaluated_event.criticality


async def test_publish_history_is_ordered_fifo(queue, evaluated_event):

    e1 = evaluated_event.model_copy(update={"criticality": 1.0, "title": "First"})
    e2 = evaluated_event.model_copy(update={"criticality": 9.0, "title": "Second"})
    await queue.publish(e1)
    await queue.publish(e2)
    assert queue.history[0]["title"] == "First"
    assert queue.history[1]["title"] == "Second"


async def test_publish_respects_maxlen(queue, evaluated_event):
    for _ in range(HISTORY_MAXLEN + 10):
        await queue.publish(evaluated_event)
    assert len(queue.history) == HISTORY_MAXLEN


async def test_publish_broadcasts_to_connected_clients(queue, evaluated_event):
    ws = AsyncMock()
    queue._connections.add(ws)

    await queue.publish(evaluated_event)

    ws.send_json.assert_called_once()
    frame = ws.send_json.call_args[0][0]
    assert frame["type"] == "event"
    assert frame["event"]["criticality"] == evaluated_event.criticality
    assert frame["event"]["category"] == evaluated_event.category


async def test_publish_broadcasts_to_multiple_clients(queue, evaluated_event):
    ws1, ws2 = AsyncMock(), AsyncMock()
    queue._connections.update({ws1, ws2})

    await queue.publish(evaluated_event)

    ws1.send_json.assert_called_once()
    ws2.send_json.assert_called_once()


async def test_publish_removes_dead_connections(queue, evaluated_event):
    ws_dead = AsyncMock()
    ws_dead.send_json.side_effect = Exception("connection closed")
    ws_alive = AsyncMock()
    queue._connections.update({ws_dead, ws_alive})

    await queue.publish(evaluated_event)

    assert ws_dead not in queue._connections
    assert ws_alive in queue._connections


# ─── connect / disconnect ─────────────────────────────────────────────────────


async def test_connect_accepts_websocket(queue):
    ws = AsyncMock()
    await queue.connect(ws)
    ws.accept.assert_called_once()


async def test_connect_sends_history_as_single_frame(queue, evaluated_event):
    await queue.publish(evaluated_event)
    await queue.publish(evaluated_event)

    ws = AsyncMock()
    await queue.connect(ws)

    # History arrives in ONE frame, distinct from live "event" frames
    ws.send_json.assert_called_once()
    frame = ws.send_json.call_args[0][0]
    assert frame["type"] == "history"
    assert len(frame["events"]) == 2
    assert frame["events"][0]["title"] == evaluated_event.title


async def test_connect_without_history_sends_empty_frame(queue):
    ws = AsyncMock()
    await queue.connect(ws)
    ws.send_json.assert_called_once_with({"type": "history", "events": []})


def test_disconnect_removes_connection(queue):
    ws = MagicMock()
    queue._connections.add(ws)
    queue.disconnect(ws)
    assert ws not in queue._connections


def test_disconnect_unknown_ws_is_safe(queue):
    ws = MagicMock()
    queue.disconnect(ws)  # should not raise


# ─── Persistence & resilience ─────────────────────────────────────────────────


async def test_history_is_persisted_and_restored(tmp_path, evaluated_event):
    from store import StateStore

    first = EventQueue()
    first.attach_store(StateStore(str(tmp_path)))
    await first.publish(evaluated_event)

    second = EventQueue()
    second.attach_store(StateStore(str(tmp_path)))
    assert [e["title"] for e in second.history] == [evaluated_event.title]


def test_attach_store_tolerates_garbage(tmp_path):
    from store import StateStore

    (tmp_path / "history.json").write_text('["not a dict", 3, {"title": "ok"}]')
    q = EventQueue()
    q.attach_store(StateStore(str(tmp_path)))
    assert q.history == [{"title": "ok"}]


def test_attach_store_twice_does_not_duplicate(tmp_path):
    from store import StateStore

    (tmp_path / "history.json").write_text('[{"title": "ok"}]')
    q = EventQueue()
    q.attach_store(StateStore(str(tmp_path)))
    q.attach_store(StateStore(str(tmp_path)))
    assert len(q.history) == 1


async def test_slow_client_is_dropped_without_blocking_others(queue, evaluated_event, monkeypatch):
    import asyncio

    import event_queue

    monkeypatch.setattr(event_queue, "SEND_TIMEOUT_S", 0.05)

    async def never(_):
        await asyncio.sleep(10)

    slow, fast = AsyncMock(), AsyncMock()
    slow.send_json.side_effect = never
    queue._connections.update({slow, fast})

    await asyncio.wait_for(queue.publish(evaluated_event), timeout=1)

    fast.send_json.assert_called_once()
    assert slow not in queue._connections and fast in queue._connections


async def test_failing_history_send_drops_the_connection(queue):
    ws = AsyncMock()
    ws.send_json.side_effect = Exception("gone")
    await queue.connect(ws)
    assert ws not in queue._connections
