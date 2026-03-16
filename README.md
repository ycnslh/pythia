# PYTHIA

> Divergence monitoring ambient display powered by an LLM.
> Inspired by the Rehoboam system from Westworld.

PYTHIA is an autonomous divergence monitoring system. It continuously ingests events from configurable sources (RSS feeds, Uptime Kuma, webhooks), evaluates their criticality using an LLM, and renders the result as a fullscreen ambient visual interface.

It is designed to run silently on a dedicated screen — no interaction, no authentication.

## Views

| Path | Description |
|---|---|
| `/display` | Fullscreen ambient display — meant for a dedicated screen |
| `/feed` | Chronological log of all evaluated events |

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
Evaluator (OpenAI-compatible API)
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

## Requirements

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- An API key for an OpenAI-compatible LLM endpoint ([OpenRouter](https://openrouter.ai) recommended)
- A GitHub Actions self-hosted runner on the target machine (for CI/CD)

## Configuration

### Environment variables

Variables are stored in GitHub Settings → Environments → `production` and injected automatically at deploy time. No `.env` file needs to be managed manually.

| Variable | Description | Default |
|---|---|---|
| `LLM_URL` | LLM endpoint (any OpenAI-compatible API) | `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | Model identifier | `nvidia/nemotron-3-super-120b-a12b:free` |
| `LLM_API_KEY` | API key for the LLM endpoint | *(secret)* |
| `PYTHIA_LANGUAGE` | UI and prompt language (`en` or `fr`) | `en` |
| `CRITICALITY_THRESHOLD` | Discard events below this score | `1` |
| `BACKEND_PORT` | Exposed port for the API | `8082` |
| `FRONTEND_PORT` | Exposed port for the frontend | `8081` |
| `SOURCES_FILE` | Path to sources config (inside container) | `sources.yaml` |

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

## Deployment

Deployment is fully automated via the GitHub Actions CI/CD pipeline on push to `main`.

The self-hosted runner runs backend and frontend tests, then:

1. Generates `.env` from the `production` GitHub Environment
2. Runs `docker compose up --build -d`
3. Waits for the backend health check
4. Runs smoke tests against `/health`, `/api/events`, and the frontend

To trigger a deploy: push to `main`.

## Adding a source

1. Create `backend/sources/my_source.py` extending `BaseSource`
2. Implement `fetch()` returning `List[RawEvent]`
3. Register the type in `backend/sources/__init__.py`
4. Add an entry in `sources.yaml`

## Criticality scale

| Range | Category |
|---|---|
| 1–3 | `NOMINAL` |
| 4–5 | `ELEVATED SCRUTINY` |
| 6–7 | `DIVERGENCE` |
| 8–9 | `INTERVENTION IN PROGRESS` |
| 10 | `CRITICAL DIVERGENCE` |
