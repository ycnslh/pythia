from sources.base import BaseSource
from sources.rss import RSSSource
from sources.uptime_kuma import UptimeKumaSource
from sources.webhook import WebhookSource

SOURCE_REGISTRY = {
    "rss": RSSSource,
    "uptime_kuma": UptimeKumaSource,
    "webhook": WebhookSource,
}


def create_source(config: dict) -> BaseSource:
    source_type = config.get("type")
    cls = SOURCE_REGISTRY.get(source_type)
    if cls is None:
        raise ValueError(f"Unknown source type: {source_type!r}")
    return cls(config)
