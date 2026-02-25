import logging
from typing import List

from fastapi import APIRouter, Request, HTTPException

from models import RawEvent
from sources.base import BaseSource

logger = logging.getLogger(__name__)


class WebhookSource(BaseSource):
    """Push-based source — events arrive via HTTP POST, not polling."""

    def get_type(self) -> str:
        return "webhook"

    async def fetch(self) -> List[RawEvent]:
        return []  # Webhooks are push-based


def build_webhook_router(configs: list, evaluate_fn, publish_fn) -> APIRouter:
    """
    Build a FastAPI router with one POST endpoint per webhook source config.

    Accepts any JSON payload. Recognized fields:
      title, description / message / text, url
    """
    router = APIRouter()

    for config in configs:
        path: str = config.get("path", "/webhook")
        name: str = config.get("name", "Webhook")

        # Use default-arg capture to avoid late-binding closure issues
        async def receive(
            request: Request,
            _name: str = name,
            _evaluate=evaluate_fn,
            _publish=publish_fn,
        ):
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")

            raw = RawEvent(
                title=body.get("title", "Webhook event"),
                description=(
                    body.get("description")
                    or body.get("message")
                    or body.get("text")
                ),
                url=body.get("url"),
                source_name=_name,
                source_type="webhook",
                raw_data=body,
            )

            evaluated = await _evaluate(raw)
            if evaluated:
                await _publish(evaluated)

            return {"status": "received"}

        router.add_api_route(
            path,
            receive,
            methods=["POST"],
            name=f"webhook_{name.lower().replace(' ', '_')}",
        )
        logger.info("Registered webhook endpoint: POST %s (%s)", path, name)

    return router
