import asyncio
import logging
from collections import deque
from typing import Set

from fastapi import WebSocket

from models import EvaluatedEvent
from store import StateStore

logger = logging.getLogger(__name__)

# Maximum number of events kept in history (sent to new WebSocket clients on connect)
HISTORY_MAXLEN = 100
# A client that cannot accept a frame within this delay is dropped
SEND_TIMEOUT_S = 5.0
HISTORY_KEY = "history"


class EventQueue:
    def __init__(self) -> None:
        self._history: deque[dict] = deque(maxlen=HISTORY_MAXLEN)
        self._connections: Set[WebSocket] = set()
        self._store: StateStore | None = None

    def attach_store(self, store: StateStore) -> None:
        """Enable persistence and restore the history saved by a previous run."""
        self._store = store
        if self._history:
            return  # already populated (attach_store called twice)
        saved = store.load(HISTORY_KEY, [])
        if isinstance(saved, list):
            for event in saved[-HISTORY_MAXLEN:]:
                if isinstance(event, dict):
                    self._history.append(event)
        if self._history:
            logger.info("Restored %d event(s) from disk", len(self._history))

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("WebSocket connected. Active connections: %d", len(self._connections))
        # Send history as ONE frame so clients can tell it apart from live events
        # (the ambient display must not re-play old events on every reconnect).
        if not await self._send(ws, {"type": "history", "events": list(self._history)}):
            self._connections.discard(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("WebSocket disconnected. Active connections: %d", len(self._connections))

    @staticmethod
    async def _send(ws: WebSocket, frame: dict) -> bool:
        try:
            await asyncio.wait_for(ws.send_json(frame), SEND_TIMEOUT_S)
            return True
        except Exception as e:
            logger.warning("Failed to send to WebSocket client: %s", e)
            return False

    async def publish(self, event: EvaluatedEvent) -> None:
        data = event.model_dump()
        self._history.append(data)
        if self._store is not None:
            self._store.save(HISTORY_KEY, list(self._history))

        frame = {"type": "event", "event": data}
        targets = list(self._connections)
        # In parallel: one slow client must not delay the others (or the poller)
        results = await asyncio.gather(*(self._send(ws, frame) for ws in targets))
        self._connections -= {ws for ws, ok in zip(targets, results, strict=False) if not ok}

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


queue = EventQueue()
