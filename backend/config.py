from pydantic_settings import BaseSettings
from typing import Any
import yaml
import os


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


def load_sources() -> list[dict[str, Any]]:
    path = os.environ.get("SOURCES_FILE", "sources.yaml")
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


settings = Settings()
