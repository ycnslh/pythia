from abc import ABC, abstractmethod
from typing import List

from models import RawEvent


class BaseSource(ABC):
    def __init__(self, config: dict) -> None:
        self.config = config

    @abstractmethod
    async def fetch(self) -> List[RawEvent]:
        """Pull new events. Return an empty list if nothing new."""
        ...

    def get_name(self) -> str:
        return self.config.get("name", self.__class__.__name__)

    def get_type(self) -> str:
        raise NotImplementedError
