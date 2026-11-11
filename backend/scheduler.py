import asyncio
import logging
from typing import List

from dedupe import TitleDeduplicator
from pipeline import process_event
from sources.base import BaseSource
from store import StateStore, state_key

logger = logging.getLogger(__name__)

# Maps source name → True (healthy) / False (last poll failed).
# Read by the /api/system endpoint.
source_health: dict[str, bool] = {}

MAX_BACKOFF_S = 3600


async def _poll_source(
    source: BaseSource,
    store: StateStore | None = None,
    dedupe: TitleDeduplicator | None = None,
) -> None:
    interval: int = source.config.get("interval", 300)
    name = source.get_name()
    key = state_key("source", name)
    logger.info("Polling started for %s (interval: %ds)", name, interval)

    if store is not None:
        saved = store.load(key)
        if isinstance(saved, dict):
            source.load_state(saved)
    last_saved = source.export_state()

    error_count = 0

    while True:
        try:
            events = await source.fetch()
            source_health[name] = True
            error_count = 0

            # Persist before evaluating: a crash mid-evaluation must not make the
            # same items be fetched and billed again on restart.
            state = source.export_state()
            if store is not None and state is not None and state != last_saved:
                store.save(key, state)
                last_saved = state

            for raw_event in events:
                # Same story from several feeds → evaluate once. Only for RSS:
                # monitoring events ("X is DOWN") legitimately repeat.
                if (
                    dedupe is not None
                    and raw_event.source_type == "rss"
                    and dedupe.check_and_add(raw_event.title)
                ):
                    logger.debug("Duplicate headline skipped: %s", raw_event.title)
                    continue
                await process_event(raw_event)
        except asyncio.CancelledError:
            logger.info("Polling cancelled for %s", name)
            return
        except Exception as e:
            source_health[name] = False
            error_count += 1
            backoff = min(interval * (2**error_count), MAX_BACKOFF_S)
            logger.error(
                "Poll failed for %s (attempt %d) — retrying in %ds: %s",
                name, error_count, backoff, e,
            )
            await asyncio.sleep(backoff)
            continue

        await asyncio.sleep(interval)


def start_scheduler(
    sources: List[BaseSource],
    store: StateStore | None = None,
    dedupe: TitleDeduplicator | None = None,
) -> List[asyncio.Task]:
    """Create and return polling tasks for all pull-based sources."""
    return [asyncio.create_task(_poll_source(s, store, dedupe)) for s in sources]
