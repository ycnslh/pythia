import logging

from config import settings
from evaluator import evaluate
from event_queue import queue
from models import RawEvent

logger = logging.getLogger(__name__)


async def process_event(raw: RawEvent):
    """Evaluate a raw event, apply the global threshold and publish it.

    Shared by the pollers and the webhook receiver. Returns the published
    EvaluatedEvent, or None if it was dropped (evaluation failed / below threshold).
    """
    evaluated = await evaluate(raw)
    if evaluated is None:
        return None
    if evaluated.criticality < settings.criticality_threshold:
        logger.debug(
            "Event below threshold (%.1f < %.1f): %s",
            evaluated.criticality,
            settings.criticality_threshold,
            evaluated.title,
        )
        return None
    logger.info(
        "[%s] criticality=%.1f category=%s — %s",
        raw.source_name,
        evaluated.criticality,
        evaluated.category,
        evaluated.title,
    )
    await queue.publish(evaluated)
    return evaluated
