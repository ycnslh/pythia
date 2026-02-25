from pydantic import BaseModel
from typing import Optional


class RawEvent(BaseModel):
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    source_name: str
    source_type: str
    raw_data: Optional[dict] = None


class EvaluatedEvent(BaseModel):
    criticality: float
    category: str
    title: str
    summary: str
    location: Optional[str] = None
    source: str
    timestamp: str
    url: Optional[str] = None
