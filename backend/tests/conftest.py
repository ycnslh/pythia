import os
import tempfile
from pathlib import Path

# Set env vars before any module imports to avoid pydantic-settings reading a
# real .env file during tests.
os.environ.setdefault("LLM_URL", "http://localhost:11434/v1")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("PYTHIA_LANGUAGE", "en")
os.environ.setdefault("CRITICALITY_THRESHOLD", "1.0")
os.environ.setdefault("DATA_DIR", "")  # persistence off unless a test opts in

# A throwaway sources file (one webhook, no pollers → no network) and a fake
# built frontend, so tests can drive the whole app.
_TMP = Path(tempfile.mkdtemp(prefix="pythia-tests-"))
(_TMP / "sources.yaml").write_text(
    "sources:\n  - type: webhook\n    name: Test Alerts\n    path: /webhook/alerts\n"
)
(_TMP / "dist" / "assets").mkdir(parents=True)
(_TMP / "dist" / "index.html").write_text("<html><head><title>PYTHIA</title></head><body>app</body></html>")
(_TMP / "dist" / "assets" / "app.js").write_text("console.log('app')")
(_TMP / "dist" / "favicon.svg").write_text("<svg/>")
(_TMP / "secret.txt").write_text("top secret")
os.environ["SOURCES_FILE"] = str(_TMP / "sources.yaml")
os.environ["STATIC_DIR"] = str(_TMP / "dist")

import pytest

from models import EvaluatedEvent, RawEvent


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


@pytest.fixture(autouse=True)
def reset_global_state():
    """The event queue and LLM health are process-wide singletons: isolate tests."""
    from evaluator import llm_health
    from event_queue import queue

    queue._history.clear()
    queue._connections.clear()
    queue._store = None
    llm_health.update(ok=None, last_success=None, last_error=None)
    yield
