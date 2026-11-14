import logging
from typing import Dict, List

from models import RawEvent
from sources.base import BaseSource

logger = logging.getLogger(__name__)


class UptimeKumaSource(BaseSource):
    """
    Polls an Uptime Kuma status page heartbeat endpoint.

    Required config keys:
      url   — base URL of Uptime Kuma, e.g. http://uptime-kuma:3001
      slug  — status page slug (found in the status page URL)

    Optional:
      api_key — if your Uptime Kuma instance requires authentication
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        # monitor_id -> last known status (1=up, 0=down)
        self._last_states: Dict[str, int] = {}

    def get_type(self) -> str:
        return "uptime_kuma"

    def export_state(self) -> dict:
        return {"last_states": self._last_states}

    def load_state(self, state: dict) -> None:
        states = state.get("last_states", {})
        if isinstance(states, dict):
            self._last_states = {str(k): int(v) for k, v in states.items()}

    async def fetch(self) -> List[RawEvent]:
        base_url = self.config["url"].rstrip("/")
        slug = self.config.get("slug", "default")
        endpoint = f"{base_url}/api/status-page/heartbeat/{slug}"

        headers = {}
        if api_key := self.config.get("api_key"):
            headers["Authorization"] = f"Bearer {api_key}"

        # Errors propagate on purpose: the scheduler flags the source unhealthy and backs off.
        resp = await self.get_if_changed(endpoint, headers)
        if resp is None:
            return []  # 304 Not Modified: no heartbeat changed, so no transition
        data = resp.json()
        self.remember_validators(resp)

        events: List[RawEvent] = []
        heartbeat_list: Dict[str, list] = data.get("heartbeatList", {})

        for monitor_id, heartbeats in heartbeat_list.items():
            if not heartbeats:
                continue

            latest = heartbeats[-1]
            status: int = latest.get("status", 1)  # 1=up, 0=down, 2=pending, 3=maintenance
            # Pending/maintenance are transient: keep the last definitive state.
            if status not in (0, 1):
                continue
            monitor_name: str = latest.get("name", f"Monitor {monitor_id}")

            previous = self._last_states.get(monitor_id)

            # Emit an event only when the status changes
            if previous is not None and status != previous:
                state_label = "UP" if status == 1 else "DOWN"
                events.append(
                    RawEvent(
                        title=f"{monitor_name} is {state_label}",
                        description=latest.get("msg") or f"Monitor transitioned to {state_label}",
                        url=base_url,
                        source_name=self.get_name(),
                        source_type=self.get_type(),
                        raw_data=latest,
                    )
                )

            self._last_states[monitor_id] = status

        return events
