"""Serve the built frontend (Vite `dist/`) from the backend: one process, one port."""

import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import settings

logger = logging.getLogger(__name__)

# Paths owned by the backend API: never answered with the SPA shell
_API_PREFIXES = ("api/", "webhook", "ws", "health")


def find_static_dir() -> Path | None:
    base = Path(__file__).resolve().parent
    candidates = [settings.static_dir] if settings.static_dir else []
    candidates += [str(base / "static"), str(base.parent / "frontend" / "dist")]
    for candidate in candidates:
        path = Path(candidate)
        if (path / "index.html").is_file():
            return path
    return None


def runtime_config() -> dict:
    """Tunables the frontend reads at runtime (injected into index.html)."""
    return {
        "language": settings.pythia_language,
        "displayThreshold": settings.display_threshold,
        "queueMax": settings.display_queue_max,
        "maxAgeS": settings.display_max_age_s,
    }


def render_index(index_html: str) -> str:
    """Inject runtime config so one image serves any language / threshold."""
    payload = json.dumps(runtime_config()).replace("<", "\\u003c")
    script = f"<script>window.__PYTHIA__={payload};</script>"
    if "</head>" in index_html:
        return index_html.replace("</head>", f"{script}</head>", 1)
    return script + index_html


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()
    index_html = (root / "index.html").read_text(encoding="utf-8")

    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith(_API_PREFIXES):
            raise HTTPException(status_code=404)
        # Real files at the root of dist/ (favicon, …), without escaping it
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        # Client-side routes (/display, /feed): HTML is re-rendered per request
        # so config changes apply without a rebuild.
        return HTMLResponse(render_index(index_html), headers={"Cache-Control": "no-cache"})

    logger.info("Serving frontend from %s", root)
