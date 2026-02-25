import re
import json
import logging
from datetime import datetime, timezone

from openai import AsyncOpenAI

from config import settings
from models import RawEvent, EvaluatedEvent

logger = logging.getLogger(__name__)

# OpenAI-compatible client pointing to Ollama (or any OpenAI-compatible LLM server)
client = AsyncOpenAI(
    base_url=f"{settings.ollama_url}/v1",
    api_key="ollama",  # Ollama does not require a real key
    timeout=120.0,  # Model cold-start on Jetson can be slow
)

SYSTEM_PROMPTS = {
    "en": """\
You are a JSON-only classification API. You MUST respond with a single JSON object and nothing else.
Do NOT write any text, explanation, summary, or commentary before or after the JSON.
Your entire response must start with { and end with }.

Classify the news event using this exact schema:
{
  "criticality": <float 1.0–10.0>,
  "category": <"NOMINAL"|"ELEVATED SCRUTINY"|"DIVERGENCE"|"INTERVENTION IN PROGRESS"|"CRITICAL DIVERGENCE">,
  "title": "<concise event title, max 10 words>",
  "summary": "<one sentence summary>",
  "location": "<city, country — or null>",
  "source": "<source name>",
  "timestamp": "<ISO 8601 UTC timestamp>"
}

Criticality scale (category MUST match):
  1–3   → NOMINAL
  4–5   → ELEVATED SCRUTINY
  6–7   → DIVERGENCE
  8–9   → INTERVENTION IN PROGRESS
  10    → CRITICAL DIVERGENCE
""",
    "fr": """\
Tu es une API de classification JSON uniquement. Tu DOIS répondre avec un seul objet JSON et rien d'autre.
N'écris AUCUN texte, explication, résumé ou commentaire avant ou après le JSON.
Ta réponse entière doit commencer par { et se terminer par }.

Classe l'événement d'actualité avec ce schéma exact :
{
  "criticality": <float 1.0–10.0>,
  "category": <"NOMINAL"|"ELEVATED SCRUTINY"|"DIVERGENCE"|"INTERVENTION IN PROGRESS"|"CRITICAL DIVERGENCE">,
  "title": "<titre court, 10 mots max>",
  "summary": "<résumé en une phrase>",
  "location": "<ville, pays — ou null>",
  "source": "<nom de la source>",
  "timestamp": "<horodatage ISO 8601 UTC>"
}

Échelle de criticité (la catégorie DOIT correspondre) :
  1–3   → NOMINAL
  4–5   → ELEVATED SCRUTINY
  6–7   → DIVERGENCE
  8–9   → INTERVENTION IN PROGRESS
  10    → CRITICAL DIVERGENCE
""",
}


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models (e.g. Qwen3)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict:
    text = _strip_thinking(text)
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back: find the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"No valid JSON found in model response: {text[:300]!r}")


async def evaluate(event: RawEvent, retries: int = 2) -> EvaluatedEvent | None:
    system_prompt = SYSTEM_PROMPTS.get(settings.pythia_language, SYSTEM_PROMPTS["en"])
    user_content = (
        f"Title: {event.title}\n"
        f"Source: {event.source_name}\n"
        f"Description: {event.description or 'N/A'}"
    )

    for attempt in range(retries + 1):
        try:
            # Use streaming to avoid timeout waiting for full response on slow hardware
            raw_chunks: list[str] = []
            stream = await client.chat.completions.create(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
                max_tokens=512,
                extra_body={
                    "think": False,
                    "options": {"num_ctx": 2048},
                },
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    raw_chunks.append(delta)

            raw = "".join(raw_chunks)
            data = _extract_json(raw)

            criticality = float(data["criticality"])
            return EvaluatedEvent(
                criticality=criticality,
                category=data["category"],
                title=data.get("title", event.title),
                summary=data["summary"],
                location=data.get("location"),
                source=data.get("source", event.source_name),
                timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                url=event.url,
            )
        except Exception as e:
            logger.warning("Evaluation attempt %d/%d failed: %s", attempt + 1, retries + 1, e)

    logger.error("All evaluation attempts failed for event: %s", event.title)
    return None
