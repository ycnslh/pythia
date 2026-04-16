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

    # Display
    pythia_language: str = "en"
    criticality_threshold: float = 1.0

    # Server
    backend_port: int = 8000

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
