# PYTHIA

> Divergence monitoring ambient display powered by a local LLM.
> Inspired by the Rehoboam system from Westworld.

---

PYTHIA is an autonomous divergence monitoring system. It continuously ingests events from configurable sources (RSS feeds, Uptime Kuma, webhooks), evaluates their criticality using a local LLM via Ollama, and renders the result as a fullscreen ambient visual interface.

It is designed to run silently on a dedicated screen — no interaction, no cloud dependency, no authentication.

---

## Views

| Path | Description |
|---|---|
| `/display` | Fullscreen ambient display — meant for a dedicated screen |
| `/feed` | Chronological log of all evaluated events |

---

## Architecture

```
External Sources
      │
      ▼
Ingestion Layer (FastAPI)
├── RSS poller
├── Uptime Kuma poller
└── Webhook receiver
      │
      ▼
Evaluator (Ollama / local LLM)
→ Returns structured JSON: { criticality, category, title, summary, location, source, timestamp }
      │
      ▼
Event Queue (in-memory)
      │
      ▼
WebSocket broadcast
      │
   ┌──┴──┐
   ▼     ▼
/display  /feed
```

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- [Ollama](https://ollama.com) running natively on the host (not inside Docker)
- A GitHub Actions self-hosted runner on the target machine (for CI/CD)

Tested on **Nvidia Jetson Orin Nano Super** (ARM64, 8 GB unified RAM).

---

## LLM Setup

PYTHIA uses a custom Ollama model called `pythia-eval`, built from Qwen3 1.7B with a baked-in evaluation system prompt.

Create the following `Modelfile` on the host machine:

```
FROM qwen3:1.7b

SYSTEM """You are a JSON-only classification API. Your sole function is to analyze news events and return a structured JSON object.

CRITICAL RULES:
- Your response MUST start with { and end with }
- Never write text, explanation, or commentary outside the JSON
- Never use markdown, code blocks, or backticks

Output schema:
{
  "criticality": <float 1.0-10.0>,
  "category": <"NOMINAL"|"ELEVATED SCRUTINY"|"DIVERGENCE"|"INTERVENTION IN PROGRESS"|"CRITICAL DIVERGENCE">,
  "title": "<event title, max 10 words>",
  "summary": "<one sentence summary>",
  "location": "<city, country or null>",
  "source": "<source name>",
  "timestamp": "<ISO 8601 UTC timestamp>"
}

Criticality scale:
1-3   → NOMINAL
4-5   → ELEVATED SCRUTINY
6-7   → DIVERGENCE
8-9   → INTERVENTION IN PROGRESS
10    → CRITICAL DIVERGENCE"""

PARAMETER temperature 0.1
PARAMETER num_ctx 2048
```

Then build and register the model:

```bash
ollama create pythia-eval -f Modelfile
ollama list  # pythia-eval should appear
```

---

## Configuration

### Environment variables

Copy `.env.example` to `~/.pythia.env` on the target machine (the CI/CD pipeline reads it from there):

```bash
cp .env.example ~/.pythia.env
nano ~/.pythia.env
```

| Variable | Description | Default |
|---|---|---|
| `OLLAMA_URL` | Ollama endpoint (host-accessible) | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | Model name in Ollama | `pythia-eval` |
| `PYTHIA_LANGUAGE` | UI and prompt language (`en` or `fr`) | `en` |
| `CRITICALITY_THRESHOLD` | Discard events below this score | `1` |
| `BACKEND_PORT` | Exposed port for the API | `8082` |
| `FRONTEND_PORT` | Exposed port for the frontend | `8081` |

### Sources

Edit `sources.yaml` to configure ingestion sources:

```yaml
sources:
  - type: rss
    name: BBC World News
    url: https://feeds.bbci.co.uk/news/world/rss.xml
    interval: 300  # seconds

  - type: uptime_kuma
    name: Homelab Monitor
    url: http://uptime-kuma:3001
    slug: default
    interval: 60

  - type: webhook
    name: Custom Alerts
    path: /webhook/alerts  # POST endpoint exposed by PYTHIA
```

---

## Deployment

Deployment is handled automatically by the GitHub Actions CI/CD pipeline on push to `main`.

The self-hosted runner on the Jetson runs tests, then:

1. Copies `~/.pythia.env` → `.env`
2. Runs `docker compose up --build -d`
3. Waits for the backend health check
4. Runs smoke tests against `/health`, `/api/events`, and the frontend

To trigger a deploy: push to `main`.

To deploy manually on the machine:

```bash
cp ~/.pythia.env .env
docker compose up --build -d
```

---

## Adding a source

1. Create `backend/sources/my_source.py` extending `BaseSource`
2. Implement `fetch()` returning `List[RawEvent]`
3. Register the type in `backend/config.py`
4. Add an entry in `sources.yaml`

---

## Criticality scale

| Range | Category |
|---|---|
| 1–3 | `NOMINAL` |
| 4–5 | `ELEVATED SCRUTINY` |
| 6–7 | `DIVERGENCE` |
| 8–9 | `INTERVENTION IN PROGRESS` |
| 10 | `CRITICAL DIVERGENCE` |
