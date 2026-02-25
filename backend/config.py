from pydantic_settings import BaseSettings
from typing import Any
import yaml
import os


class Settings(BaseSettings):
    # Ollama — OpenAI-compatible endpoint
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

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
