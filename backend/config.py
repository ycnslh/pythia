import logging
import os
from functools import lru_cache
from typing import Any

import yaml
from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM — OpenAI-compatible endpoint (OpenRouter or any compatible server)
    llm_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    llm_api_key: str = ""
    # Max simultaneous LLM requests (protects rate-limited / free-tier endpoints)
    llm_concurrency: int = 2

    # Display
    pythia_language: str = "en"
    # Events below this score are discarded entirely (not shown in /feed either)
    criticality_threshold: float = 1.0
    # Events below this score appear in /feed only, never on the ambient /display
    display_threshold: float = 4.0
    # /display pending queue: max waiting events, and max age before one is dropped
    display_queue_max: int = 10
    display_max_age_s: int = 600

    # Persistence: history + source state survive restarts. Empty string disables it.
    data_dir: str = "data"

    # Built frontend served by the backend. Empty = auto-detect (./static, ../frontend/dist)
    static_dir: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def check_required(self) -> "Settings":
        if not self.llm_api_key:
            logging.getLogger(__name__).warning(
                "LLM_API_KEY is not set — LLM evaluation calls will fail with 401"
            )
        return self


@lru_cache(maxsize=1)
def load_sources() -> list[dict[str, Any]]:
    path = os.environ.get("SOURCES_FILE", "sources.yaml")
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        logging.getLogger(__name__).warning(
            "sources.yaml not found at %s — starting with no sources", path
        )
        return []
    return data.get("sources", []) if isinstance(data, dict) else []


settings = Settings()
