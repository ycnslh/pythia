from abc import ABC, abstractmethod
from typing import List

import httpx

from models import RawEvent


class BaseSource(ABC):
    # Defaults for the HTTP client of pull sources; subclasses may override.
    http_timeout: float = 10.0
    http_follow_redirects: bool = False
    http_headers: dict[str, str] = {}

    def __init__(self, config: dict):
        self.config = config
        # Created on first use (push-based sources never open one) and reused for
        # every poll, so TCP/TLS connections are kept alive between intervals.
        self._client: httpx.AsyncClient | None = None
        # Cache validators of the last successfully processed response.
        self._etag: str | None = None
        self._last_modified: str | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.http_timeout,
                follow_redirects=self.http_follow_redirects,
                headers=self.http_headers,
            )
        return self._client

    async def aclose(self) -> None:
        """Release the HTTP client. Called once at shutdown."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_if_changed(
        self, url: str, headers: dict[str, str] | None = None
    ) -> httpx.Response | None:
        """GET `url`, sending the remembered ETag / Last-Modified if any.

        Returns None on `304 Not Modified` (nothing changed, not an error). Other
        HTTP errors raise. The validators are only updated by remember_validators(),
        so the caller decides when a response counts as fully processed.
        """
        request_headers = dict(headers or {})
        if self._etag:
            request_headers["If-None-Match"] = self._etag
        if self._last_modified:
            request_headers["If-Modified-Since"] = self._last_modified
        resp = await self.client.get(url, headers=request_headers)
        if resp.status_code == 304:
            return None
        resp.raise_for_status()
        return resp

    def remember_validators(self, resp: httpx.Response) -> None:
        """Store the cache validators of `resp` (or clear them if it has none)."""
        self._etag = resp.headers.get("ETag") or None
        self._last_modified = resp.headers.get("Last-Modified") or None

    def forget_validators(self) -> None:
        self._etag = None
        self._last_modified = None

    @abstractmethod
    async def fetch(self) -> List[RawEvent]:
        """Pull new events from this source. Return empty list if nothing new.

        Raise on failure (network, HTTP, parsing): the scheduler flags the source
        unhealthy and backs off.
        """
        pass

    def get_name(self) -> str:
        return self.config.get("name", self.__class__.__name__)

    # Optional persistence hooks. A source returning a JSON-serialisable dict from
    # export_state() gets it saved after each poll and handed back to load_state()
    # on the next start (e.g. already-seen ids, last known statuses).
    def export_state(self) -> dict | None:
        return None

    def load_state(self, state: dict) -> None:  # noqa: B027 — optional hook, no-op by default
        pass
