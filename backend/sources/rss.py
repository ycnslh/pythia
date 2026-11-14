import asyncio
import hashlib
import logging
from collections import OrderedDict
from datetime import UTC, datetime
from typing import List

import feedparser

from models import RawEvent
from sources.base import BaseSource

logger = logging.getLogger(__name__)


def _entry_published_at(entry) -> str | None:
    """Return the entry's publication date as an ISO 8601 UTC string, or None."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=UTC).isoformat()
    except Exception:
        return None


# Maximum entries processed per poll to avoid bursts
MAX_ENTRIES = 5
# Cap on _seen OrderedDict size to bound memory usage (evicts oldest entries first)
SEEN_CAP = 2000
SEEN_TRIM = 1000
# Network timeout (seconds) for downloading a feed
FETCH_TIMEOUT = 15.0
USER_AGENT = "PYTHIA/0.1 (+rss)"


class RSSSource(BaseSource):
    http_timeout = FETCH_TIMEOUT
    http_follow_redirects = True
    http_headers = {"User-Agent": USER_AGENT}

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._seen: OrderedDict[str, None] = OrderedDict()
        # False until the first successful poll (or restored state): that first poll
        # only emits the newest entries and swallows the older backlog.
        self._primed = False
        # Response whose validators become current once its entries were processed.
        self._pending_response = None

    def get_type(self) -> str:
        return "rss"

    def export_state(self) -> dict:
        return {
            "seen": list(self._seen),
            "etag": self._etag,
            "last_modified": self._last_modified,
        }

    def load_state(self, state: dict) -> None:
        seen = state.get("seen", [])
        if isinstance(seen, list):
            self._seen = OrderedDict((str(uid), None) for uid in seen[-SEEN_CAP:])
            self._primed = bool(self._seen)
        etag = state.get("etag")
        last_modified = state.get("last_modified")
        self._etag = etag if isinstance(etag, str) else None
        self._last_modified = last_modified if isinstance(last_modified, str) else None

    async def _download(self) -> bytes | None:
        """Download the feed with a bounded timeout. Raises on network/HTTP errors.

        Returns None when the server answers 304 Not Modified. Validators are only
        sent once a first poll succeeded: before that the backlog is not baselined.
        """
        if not self._primed:
            self.forget_validators()
        resp = await self.get_if_changed(self.config["url"])
        if resp is None:
            return None
        self._pending_response = resp
        return resp.content

    async def fetch(self) -> List[RawEvent]:
        """
        Errors (network, HTTP status, unparseable feed) are raised on purpose:
        the scheduler uses them to flag the source unhealthy and back off.
        """
        self._pending_response = None
        content = await self._download()
        if content is None:
            return []  # 304 Not Modified: nothing to parse, nothing new
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, content)

        if feed.get("bozo") and not feed.entries:
            raise ValueError(f"Unparseable feed: {feed.get('bozo_exception')!r}")

        events: List[RawEvent] = []
        new_entries = 0
        first_poll = not self._primed
        backlog_left = False

        for entry in feed.entries:
            uid = (
                entry.get("id")
                or entry.get("link")
                or hashlib.md5(entry.get("title", "").encode()).hexdigest()
            )

            if uid in self._seen:
                continue
            if new_entries >= MAX_ENTRIES:
                if first_poll:
                    # Baseline: a feed holds dozens of old items; do not drip-feed
                    # them to the LLM five at a time over the next polls.
                    self._seen[uid] = None
                    continue
                backlog_left = True
                break
            self._seen[uid] = None
            new_entries += 1

            events.append(
                RawEvent(
                    title=entry.get("title", "Untitled"),
                    description=entry.get("summary") or entry.get("description"),
                    url=entry.get("link"),
                    source_name=self.get_name(),
                    source_type=self.get_type(),
                    raw_data={
                        "feed_title": feed.feed.get("title", ""),
                        "published_at": _entry_published_at(entry),
                    },
                )
            )

        self._primed = True

        # Only trust a 304 later if every entry of this response was consumed. With a
        # backlog left (more than MAX_ENTRIES new), the next poll must download again.
        if self._pending_response is not None and not backlog_left:
            self.remember_validators(self._pending_response)
        else:
            self.forget_validators()
        self._pending_response = None

        # Trim _seen to avoid unbounded growth — remove oldest entries first
        if len(self._seen) > SEEN_CAP:
            while len(self._seen) > SEEN_TRIM:
                self._seen.popitem(last=False)

        return events
