from unittest.mock import AsyncMock, patch

from event_queue import queue
from pipeline import process_event


async def test_publishes_evaluated_event(raw_event, evaluated_event):
    with patch("pipeline.evaluate", AsyncMock(return_value=evaluated_event)):
        result = await process_event(raw_event)

    assert result is evaluated_event
    assert queue.history[0]["title"] == evaluated_event.title


async def test_failed_evaluation_publishes_nothing(raw_event):
    with patch("pipeline.evaluate", AsyncMock(return_value=None)):
        assert await process_event(raw_event) is None
    assert queue.history == []


async def test_events_below_global_threshold_are_dropped(raw_event, evaluated_event):
    with patch("pipeline.evaluate", AsyncMock(return_value=evaluated_event)), \
         patch("pipeline.settings") as settings:
        settings.criticality_threshold = 9.0  # evaluated_event is 7.5
        assert await process_event(raw_event) is None
    assert queue.history == []
