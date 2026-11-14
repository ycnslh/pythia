import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from config import load_sources, settings
from dedupe import TitleDeduplicator
from evaluator import llm_health
from event_queue import queue
from hardware import get_metrics
from pipeline import process_event
from scheduler import source_health, start_scheduler
from sources import create_source
from sources.webhook import build_webhook_router
from static import find_static_dir, mount_frontend
from store import StateStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    source_configs = load_sources()

    store = StateStore(settings.data_dir)
    queue.attach_store(store)
    dedupe = TitleDeduplicator(store)

    pull_sources = [
        create_source(cfg)
        for cfg in source_configs
        if cfg.get("type") != "webhook"
    ]
    webhook_configs = [cfg for cfg in source_configs if cfg.get("type") == "webhook"]

    # Mount webhook routes dynamically
    if webhook_configs:
        app.include_router(build_webhook_router(webhook_configs, process_fn=process_event))

    # The SPA catch-all goes last so it never shadows the API or webhook routes
    static_dir = find_static_dir()
    if static_dir is not None:
        mount_frontend(app, static_dir)
    else:
        logger.warning("No built frontend found — serving the API only")

    tasks = start_scheduler(pull_sources, store, dedupe)
    logger.info(
        "PYTHIA started — %d pull source(s), %d webhook(s)",
        len(pull_sources),
        len(webhook_configs),
    )

    yield

    for task in tasks:
        task.cancel()
    # Let the pollers unwind before closing the HTTP clients they may be using.
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.gather(*(s.aclose() for s in pull_sources), return_exceptions=True)


app = FastAPI(title="PYTHIA", version="0.2.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "connections": queue.connection_count,
        "llm": llm_health["ok"],
    }


@app.get("/api/events")
async def get_events():
    """Return current event history (for initial page load without WebSocket)."""
    return {"events": queue.history}


def _llm_provider(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "openrouter" in host:
        return "OpenRouter"
    if "openai.com" in host:
        return "OpenAI"
    if "anthropic" in host:
        return "Anthropic"
    if "googleapis" in host or host.endswith("google.com"):
        return "Google"
    if "ollama" in host:
        return "Ollama"
    if host in ("localhost", "127.0.0.1", "0.0.0.0", ""):
        return "Local"
    return host


@app.get("/api/system")
async def system_status():
    """Return machine resource usage and source health status."""
    metrics = await get_metrics()
    source_configs = load_sources()
    metrics["sources"] = [
        {
            "name": s.get("name", "Unknown"),
            "type": s.get("type", "unknown"),
            "healthy": source_health.get(s.get("name", ""), True),
        }
        for s in source_configs
        if s.get("type") != "webhook"
    ]
    metrics["llm"] = {
        "provider": _llm_provider(settings.llm_url),
        "model": settings.llm_model,
        # None until the first evaluation, then True/False
        "healthy": llm_health["ok"],
    }
    return metrics


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await queue.connect(ws)
    try:
        while True:
            # Keep the connection alive; actual data flows server → client
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket closed with an error", exc_info=True)
    finally:
        queue.disconnect(ws)
