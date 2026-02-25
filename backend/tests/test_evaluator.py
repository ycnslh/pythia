from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evaluator import _extract_json, _strip_thinking, evaluate

# ─── Helpers ──────────────────────────────────────────────────────────────────

VALID_LLM_RESPONSE = (
    '{"criticality": 6.5, "category": "DIVERGENCE", '
    '"title": "Flood in Tokyo", '
    '"summary": "Heavy rains caused widespread flooding.", '
    '"location": "Tokyo, Japan", "source": "Test Source", '
    '"timestamp": "2025-01-01T12:00:00Z"}'
)


class FakeChunk:
    """Mimics a streaming chunk from the OpenAI SDK."""

    def __init__(self, content: str):
        self.choices = [SimpleNamespace(delta=SimpleNamespace(content=content))]


class FakeStream:
    """Async context manager + async iterator simulating OpenAI streaming."""

    def __init__(self, text: str):
        # Split into small chunks to simulate partial delivery
        self._chunks = [text[i : i + 40] for i in range(0, len(text), 40)]
        self._idx = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        chunk = FakeChunk(self._chunks[self._idx])
        self._idx += 1
        return chunk


# ─── _strip_thinking ──────────────────────────────────────────────────────────


def test_strip_thinking_removes_block():
    text = "<think>internal reasoning here</think>{}"
    result = _strip_thinking(text)
    assert "internal reasoning" not in result
    assert "{}" in result


def test_strip_thinking_no_block():
    text = '{"key": "value"}'
    assert _strip_thinking(text) == text


def test_strip_thinking_multiline_block():
    text = "<think>\nline 1\nline 2\n</think>\n{}"
    result = _strip_thinking(text)
    assert "line 1" not in result
    assert "{}" in result


def test_strip_thinking_multiple_blocks():
    text = "<think>first</think>data<think>second</think>"
    result = _strip_thinking(text)
    assert "first" not in result
    assert "second" not in result
    assert "data" in result


# ─── _extract_json ────────────────────────────────────────────────────────────


def test_extract_json_direct_parse():
    text = '{"criticality": 5.0, "category": "ELEVATED SCRUTINY"}'
    data = _extract_json(text)
    assert data["criticality"] == 5.0
    assert data["category"] == "ELEVATED SCRUTINY"


def test_extract_json_with_surrounding_text():
    text = 'Sure, here is the result: {"criticality": 3.0, "category": "NOMINAL"} done.'
    data = _extract_json(text)
    assert data["criticality"] == 3.0


def test_extract_json_after_think_block():
    text = '<think>let me think...</think>{"criticality": 8.0, "category": "INTERVENTION IN PROGRESS"}'
    data = _extract_json(text)
    assert data["criticality"] == 8.0


def test_extract_json_raises_on_no_json():
    with pytest.raises(ValueError, match="No valid JSON"):
        _extract_json("This is not JSON at all")


def test_extract_json_raises_on_empty():
    with pytest.raises(ValueError, match="No valid JSON"):
        _extract_json("")


# ─── evaluate() ───────────────────────────────────────────────────────────────


async def test_evaluate_happy_path(raw_event):
    with patch("evaluator.client") as mock_client:
        mock_client.chat.completions.stream.return_value = FakeStream(VALID_LLM_RESPONSE)

        result = await evaluate(raw_event)

    assert result is not None
    assert result.criticality == 6.5
    assert result.category == "DIVERGENCE"
    assert result.title == "Flood in Tokyo"
    assert result.location == "Tokyo, Japan"
    assert result.timestamp == "2025-01-01T12:00:00Z"
    assert result.url == raw_event.url


async def test_evaluate_retries_on_invalid_json(raw_event):
    with patch("evaluator.client") as mock_client:
        mock_client.chat.completions.stream.side_effect = [
            FakeStream("not valid json"),
            FakeStream(VALID_LLM_RESPONSE),
        ]

        result = await evaluate(raw_event, retries=2)

    assert result is not None
    assert mock_client.chat.completions.stream.call_count == 2


async def test_evaluate_returns_none_when_all_attempts_fail(raw_event):
    with patch("evaluator.client") as mock_client:
        mock_client.chat.completions.stream.return_value = FakeStream("bad response")

        result = await evaluate(raw_event, retries=1)

    assert result is None
    assert mock_client.chat.completions.stream.call_count == 2  # 1 + 1 retry


async def test_evaluate_falls_back_to_event_title_when_missing(raw_event):
    """If the LLM omits 'title', the raw event title is used."""
    response_no_title = (
        '{"criticality": 4.0, "category": "ELEVATED SCRUTINY", '
        '"summary": "Summary.", "source": "S", "timestamp": "2025-01-01T00:00:00Z"}'
    )
    with patch("evaluator.client") as mock_client:
        mock_client.chat.completions.stream.return_value = FakeStream(response_no_title)

        result = await evaluate(raw_event)

    assert result is not None
    assert result.title == raw_event.title
