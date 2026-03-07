import logging
from contextlib import asynccontextmanager

import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings, load_sources
from event_queue import queue
from evaluator import evaluate
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
    return {"status": "ok", "connections": len(queue._connections)}


@app.get("/api/events")
async def get_events():
    """Return current event history (for initial page load without WebSocket)."""
    return {"events": queue.history}


@app.get("/api/system")
async def system_status():
    """Return machine resource usage and source health status."""
    vm = psutil.virtual_memory()
    source_configs = load_sources()
    sources_info = [
        {
            "name": s.get("name", "Unknown"),
            "type": s.get("type", "unknown"),
            "healthy": source_health.get(s.get("name", ""), True),
        }
        for s in source_configs
        if s.get("type") != "webhook"
    ]
    return {
        "cpu": psutil.cpu_percent(interval=0.1),
        "ram_pct": vm.percent,
        "ram_used_mb": vm.used // (1024 * 1024),
        "ram_total_mb": vm.total // (1024 * 1024),
        "sources": sources_info,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await queue.connect(ws)
    try:
        while True:
            # Keep the connection alive; actual data flows server → client
            await ws.receive_text()
    except WebSocketDisconnect:
        queue.disconnect(ws)
