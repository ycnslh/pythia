import asyncio
import logging
from typing import Awaitable, Callable, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from models import RawEvent
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# Webhook payloads are small JSON documents; refuse anything larger
MAX_BODY_BYTES = 64 * 1024


class WebhookSource(BaseSource):
    """Push-based source — events arrive via HTTP POST, not polling."""

    def get_type(self) -> str:
        return "webhook"

    async def fetch(self) -> List[RawEvent]:
        return []  # Webhooks are push-based


def build_webhook_router(
    configs: list,
    process_fn: Callable[[RawEvent], Awaitable[object]],
) -> APIRouter:
    """
    Build a FastAPI router with one POST endpoint per webhook source config.

    Accepts any JSON object. Recognized fields:
      title, description / message / text, url

    The endpoint answers 202 immediately; evaluation (which can take a while on
    a slow LLM) runs in the background and the result shows up on the displays.
    """
    router = APIRouter()
    background: set[asyncio.Task] = set()  # keeps task references alive until done

    async def run(raw: RawEvent) -> None:
        try:
            await process_fn(raw)
        except Exception:
            logger.exception("Webhook event processing failed: %s", raw.title)

    for config in configs:
        path: str = config.get("path", "/webhook")
        if not path.startswith("/"):
            path = "/" + path
        name: str = config.get("name", "Webhook")

        # Default-arg capture to avoid late-binding closure issues
        async def receive(request: Request, _name: str = name):
            raw_body = await request.body()
            if len(raw_body) > MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Payload too large")
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")
            if not isinstance(body, dict):
                raise HTTPException(status_code=400, detail="JSON body must be an object")

            description = body.get("description") or body.get("message") or body.get("text")
            url = body.get("url")
            raw = RawEvent(
                title=str(body.get("title") or "Webhook event"),
                description=None if description is None else str(description),
                url=url if isinstance(url, str) else None,
                source_name=_name,
                source_type="webhook",
                raw_data=body,
            )

            task = asyncio.create_task(run(raw))
            background.add(task)
            task.add_done_callback(background.discard)
            return JSONResponse({"status": "accepted"}, status_code=202)

        router.add_api_route(
            path,
            receive,
            methods=["POST"],
            name=f"webhook_{name.lower().replace(' ', '_')}",
        )
        logger.info("Registered webhook endpoint: POST %s (%s)", path, name)

    return router
