import asyncio
import hashlib
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import List

import feedparser
import httpx

from models import RawEvent
from sources.base import BaseSource

logger = logging.getLogger(__name__)


def _entry_published_at(entry) -> str | None:
    """Return the entry's publication date as an ISO 8601 UTC string, or None."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
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
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._seen: OrderedDict[str, None] = OrderedDict()

    def get_type(self) -> str:
        return "rss"

    async def _download(self) -> bytes:
        """Download the feed with a bounded timeout. Raises on network/HTTP errors."""
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        ) as client:
            resp = await client.get(self.config["url"])
            resp.raise_for_status()
            return resp.content

    async def fetch(self) -> List[RawEvent]:
        """
        Errors (network, HTTP status, unparseable feed) are raised on purpose:
        the scheduler uses them to flag the source unhealthy and back off.
        """
        content = await self._download()
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, content)

        if feed.get("bozo") and not feed.entries:
            raise ValueError(f"Unparseable feed: {feed.get('bozo_exception')!r}")

        events: List[RawEvent] = []
        new_entries = 0

        for entry in feed.entries:
            if new_entries >= MAX_ENTRIES:
                break

            uid = (
                entry.get("id")
                or entry.get("link")
                or hashlib.md5(entry.get("title", "").encode()).hexdigest()
            )

            if uid in self._seen:
                continue
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

        # Trim _seen to avoid unbounded growth — remove oldest entries first
        if len(self._seen) > SEEN_CAP:
            while len(self._seen) > SEEN_TRIM:
                self._seen.popitem(last=False)

        return events
