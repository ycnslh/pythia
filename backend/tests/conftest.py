import os

# Set env vars before any module imports to avoid pydantic-settings reading a
# real .env file during tests.
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "test-model")
os.environ.setdefault("PYTHIA_LANGUAGE", "en")
os.environ.setdefault("CRITICALITY_THRESHOLD", "1.0")

import pytest
from models import RawEvent, EvaluatedEvent


@pytest.fixture
def raw_event():
    return RawEvent(
        title="Severe flooding in central Tokyo",
        description="Heavy rains caused widespread flooding in downtown Tokyo.",
        url="https://example.com/flood-tokyo",
        source_name="Test Source",
        source_type="rss",
    )


@pytest.fixture
def evaluated_event():
    return EvaluatedEvent(
        criticality=7.5,
        category="DIVERGENCE",
        title="Severe flooding in central Tokyo",
        summary="Heavy rains caused widespread flooding in downtown Tokyo.",
        location="Tokyo, Japan",
        source="Test Source",
        timestamp="2025-01-01T00:00:00Z",
        url="https://example.com/flood-tokyo",
    )
