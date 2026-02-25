from unittest.mock import AsyncMock, MagicMock

import pytest

from event_queue import EventQueue, HISTORY_MAXLEN


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
    from models import EvaluatedEvent

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
    payload = ws.send_json.call_args[0][0]
    assert payload["criticality"] == evaluated_event.criticality
    assert payload["category"] == evaluated_event.category


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


async def test_connect_replays_history(queue, evaluated_event):
    await queue.publish(evaluated_event)

    ws = AsyncMock()
    await queue.connect(ws)

    # History replay: send_json called once for the existing event
    ws.send_json.assert_called_once()
    payload = ws.send_json.call_args[0][0]
    assert payload["title"] == evaluated_event.title


async def test_connect_no_history_no_replay(queue):
    ws = AsyncMock()
    await queue.connect(ws)
    ws.send_json.assert_not_called()


def test_disconnect_removes_connection(queue):
    ws = MagicMock()
    queue._connections.add(ws)
    queue.disconnect(ws)
    assert ws not in queue._connections


def test_disconnect_unknown_ws_is_safe(queue):
    ws = MagicMock()
    queue.disconnect(ws)  # should not raise
