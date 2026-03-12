from pydantic_settings import BaseSettings
from typing import Any
import yaml
import os


class Settings(BaseSettings):
    # LLM — OpenAI-compatible endpoint (vLLM, Ollama, or any compatible server)
    llm_url: str = "http://localhost:8080"
    llm_model: str = "mistralai/Ministral-3-3B-Reasoning-2512"

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
