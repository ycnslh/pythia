from abc import ABC, abstractmethod
from typing import List

from models import RawEvent


class BaseSource(ABC):
    def __init__(self, config: dict):
        self.config = config

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
