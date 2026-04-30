import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings, load_sources
from event_queue import queue
from evaluator import evaluate
from hardware import get_metrics
from scheduler import start_scheduler, source_health
from sources import create_source
from sources.webhook import build_webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    source_configs = load_sources()

    pull_sources = [
        create_source(cfg)
        for cfg in source_configs
        if cfg.get("type") != "webhook"
    ]
    webhook_configs = [cfg for cfg in source_configs if cfg.get("type") == "webhook"]

    # Mount webhook routes dynamically
    if webhook_configs:
        webhook_router = build_webhook_router(
            webhook_configs,
            evaluate_fn=evaluate,
            publish_fn=queue.publish,
        )
        app.include_router(webhook_router)

    tasks = start_scheduler(pull_sources)
    logger.info(
        "PYTHIA started — %d pull source(s), %d webhook(s)",
        len(pull_sources),
        len(webhook_configs),
    )

    yield

    for task in tasks:
        task.cancel()


app = FastAPI(title="PYTHIA", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local network only — no auth needed
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "connections": queue.connection_count}


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
        queue.disconnect(ws)
