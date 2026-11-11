import logging
from collections import deque
from typing import Set

from fastapi import WebSocket

from models import EvaluatedEvent

logger = logging.getLogger(__name__)

# Maximum number of events kept in history (sent to new WebSocket clients on connect)
HISTORY_MAXLEN = 100


class EventQueue:
    def __init__(self) -> None:
        self._history: deque[dict] = deque(maxlen=HISTORY_MAXLEN)
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("WebSocket connected. Active connections: %d", len(self._connections))
        # Send history as ONE frame so clients can tell it apart from live events
        # (the ambient display must not re-play old events on every reconnect).
        try:
            await ws.send_json({"type": "history", "events": list(self._history)})
        except Exception:
            pass

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("WebSocket disconnected. Active connections: %d", len(self._connections))

    async def publish(self, event: EvaluatedEvent) -> None:
        data = event.model_dump()
        self._history.append(data)
        frame = {"type": "event", "event": data}

        dead: Set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await ws.send_json(frame)
            except Exception as e:
                logger.warning("Failed to send to WebSocket client: %s", e)
                dead.add(ws)

        self._connections -= dead

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


queue = EventQueue()
