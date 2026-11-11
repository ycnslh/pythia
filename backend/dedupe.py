"""Near-duplicate detection for headlines, so one story is not evaluated twice."""

import re
import time
from collections import deque

from store import StateStore

WINDOW_S = 24 * 3600
MAX_ENTRIES = 300
SIMILARITY = 0.6
MIN_TOKENS = 3  # shorter titles are only compared for exact equality

_TOKEN = re.compile(r"[^\W_]{3,}", re.UNICODE)


def _tokens(title: str) -> frozenset[str]:
    return frozenset(_TOKEN.findall(title.lower()))


def _similar(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) < MIN_TOKENS or len(b) < MIN_TOKENS:
        return False
    return len(a & b) / len(a | b) >= SIMILARITY


class TitleDeduplicator:
    """Remembers recent titles (24h) and flags near-duplicates by Jaccard similarity."""

    def __init__(self, store: StateStore | None = None, key: str = "recent_titles") -> None:
        self._store = store
        self._key = key
        self._entries: deque[tuple[float, str]] = deque(maxlen=MAX_ENTRIES)
        if store is not None:
            for item in store.load(key, []) or []:
                try:
                    self._entries.append((float(item[0]), str(item[1])))
                except (TypeError, ValueError, IndexError):
                    continue

    def check_and_add(self, title: str, now: float | None = None) -> bool:
        """Return True if `title` duplicates a recent one; otherwise remember it."""
        now = time.time() if now is None else now
        while self._entries and now - self._entries[0][0] > WINDOW_S:
            self._entries.popleft()

        tokens = _tokens(title)
        if any(_similar(tokens, _tokens(known)) for _, known in self._entries):
            return True

        self._entries.append((now, title))
        if self._store is not None:
            self._store.save(self._key, list(self._entries))
        return False
