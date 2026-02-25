import asyncio
import hashlib
import logging
from typing import List, Set

import feedparser

from models import RawEvent
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# Maximum entries processed per poll to avoid bursts
MAX_ENTRIES = 5
# Cap on _seen set size to bound memory usage
SEEN_CAP = 2000
SEEN_TRIM = 1000


class RSSSource(BaseSource):
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._seen: Set[str] = set()

    def get_type(self) -> str:
        return "rss"

    async def fetch(self) -> List[RawEvent]:
        url = self.config["url"]
        loop = asyncio.get_event_loop()

        try:
            feed = await loop.run_in_executor(None, feedparser.parse, url)
        except Exception as e:
            logger.error("RSS fetch error for %s: %s", self.get_name(), e)
            return []

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
            self._seen.add(uid)
            new_entries += 1

            events.append(
                RawEvent(
                    title=entry.get("title", "Untitled"),
                    description=entry.get("summary") or entry.get("description"),
                    url=entry.get("link"),
                    source_name=self.get_name(),
                    source_type=self.get_type(),
                    raw_data={"feed_title": feed.feed.get("title", "")},
                )
            )

        # Trim _seen to avoid unbounded growth
        if len(self._seen) > SEEN_CAP:
            self._seen = set(list(self._seen)[-SEEN_TRIM:])

        return events
