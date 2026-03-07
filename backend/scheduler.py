import asyncio
import logging
from typing import List

from sources.base import BaseSource
from evaluator import evaluate
from event_queue import queue
from config import settings

logger = logging.getLogger(__name__)

# Maps source name → True (healthy) / False (last poll failed).
# Read by the /api/system endpoint.
source_health: dict[str, bool] = {}


async def _poll_source(source: BaseSource) -> None:
    interval: int = source.config.get("interval", 300)
    name = source.get_name()
    logger.info("Polling started for %s (interval: %ds)", name, interval)

    while True:
        try:
            events = await source.fetch()
            source_health[name] = True
            for raw_event in events:
                evaluated = await evaluate(raw_event)
                if evaluated is None:
                    continue
                if evaluated.criticality < settings.criticality_threshold:
                    logger.debug(
                        "Event below threshold (%.1f < %.1f): %s",
                        evaluated.criticality,
                        settings.criticality_threshold,
                        evaluated.title,
                    )
                    continue
                logger.info(
                    "[%s] criticality=%.1f category=%s — %s",
                    name,
                    evaluated.criticality,
                    evaluated.category,
                    evaluated.title,
                )
                await queue.publish(evaluated)
        except asyncio.CancelledError:
            logger.info("Polling cancelled for %s", name)
            return
        except Exception as e:
            source_health[name] = False
            logger.error("Unhandled error polling %s: %s", name, e)

        await asyncio.sleep(interval)


def start_scheduler(sources: List[BaseSource]) -> List[asyncio.Task]:
    """Create and return polling tasks for all pull-based sources."""
    return [asyncio.create_task(_poll_source(s)) for s in sources]
