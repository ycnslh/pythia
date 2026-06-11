# PYTHIA

> Divergence monitoring ambient display powered by an LLM.
> Inspired by the Rehoboam system from Westworld.

---

## Project Overview

PYTHIA is an autonomous divergence monitoring system. It continuously ingests events from multiple configurable sources (RSS feeds, Uptime Kuma, webhooks), evaluates their criticality using an OpenAI-compatible LLM endpoint (OpenRouter by default), and displays the result as an ambient visual interface.

The system has two views:
- `/display` — fullscreen ambient display meant to run on a dedicated screen, no interaction required
- `/feed` — chronological log of all evaluated events, readable from any browser

PYTHIA is designed to run autonomously and silently. It is not a chatbot. The LLM is used strictly for structured evaluation, not conversation.

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
Evaluator (OpenAI-compatible API, streaming)
→ Returns structured JSON: { criticality, category, title, summary, location, source, timestamp }
      │
      ▼
Event Queue (in-memory deque, last 100 events)
      │
      ▼
WebSocket broadcast
      │
   ┌──┴──┐
   ▼     ▼
/display  /feed
```

---

## Directory Structure

```
pythia/
├── backend/
│   ├── main.py               # FastAPI app, lifespan, WebSocket, REST routes
│   ├── evaluator.py          # LLM call (streaming) + robust JSON parsing
│   ├── event_queue.py        # In-memory queue + WebSocket broadcast
│   ├── scheduler.py          # Polling loop, error backoff, source health
│   ├── hardware.py           # CPU/RAM/disk/GPU/thermal metrics (psutil + Linux sysfs)
│   ├── config.py             # Pydantic Settings (.env) + sources.yaml loader
│   ├── models.py             # RawEvent, EvaluatedEvent
│   ├── sources/
│   │   ├── __init__.py       # SOURCE_REGISTRY + create_source() factory
│   │   ├── base.py           # Abstract BaseSource class
│   │   ├── rss.py            # RSSSource
│   │   ├── uptime_kuma.py    # UptimeKumaSource
│   │   └── webhook.py        # WebhookSource (FastAPI router)
│   └── tests/                # pytest (evaluator, event_queue, rss source)
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Display.jsx   # /display — ambient fullscreen view + event queue
│   │   │   └── Feed.jsx      # /feed — event log view
│   │   ├── components/
│   │   │   ├── PythiaCircle.jsx   # Canvas 2D geodesic sphere (Fibonacci mesh)
│   │   │   ├── HUDOverlay.jsx     # HUD text layer + data block
│   │   │   └── SystemPanel.jsx    # Live system metrics (polls /api/system)
│   │   ├── hooks/
│   │   │   └── useWebSocket.js    # Single WebSocket connection + reconnect
│   │   ├── i18n/
│   │   │   ├── en.js
│   │   │   └── fr.js
│   │   ├── __tests__/             # vitest (i18n keys)
│   │   └── App.jsx
│   ├── index.html
│   └── vite.config.js        # Dev proxy: /ws and /api → localhost:8000
├── scripts/
│   └── check-env.sh          # Validate .env against .env.example
├── docs/
│   └── screenshot-display.png    # README screenshot
├── sources.yaml              # Source definitions (mounted read-only in Docker)
├── .env                      # Local environment variables (gitignored)
├── .env.example              # Documented example (committed)
├── docker-compose.yml
├── README.md
├── SETUP.md
└── CLAUDE.md
```

---

## Source Plugin System

Every source extends `BaseSource` from `sources/base.py`.

### BaseSource interface

```python
from abc import ABC, abstractmethod
from typing import List
from models import RawEvent

class BaseSource(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def fetch(self) -> List[RawEvent]:
        """Pull new events from this source. Return empty list if nothing new."""
        pass

    def get_name(self) -> str:
        return self.config.get("name", self.__class__.__name__)
```

### RawEvent model

```python
class RawEvent(BaseModel):
    title: str
    description: str | None
    url: str | None
    source_name: str
    source_type: str
    raw_data: dict | None
```

### Implemented sources

| Type | File | Behavior |
|---|---|---|
| `rss` | `sources/rss.py` | Polls feed every `interval`s, dedup by entry id/link/title hash, max 5 entries per poll |
| `uptime_kuma` | `sources/uptime_kuma.py` | Polls `/api/status-page/heartbeat/{slug}`, emits an event only on up/down transitions |
| `webhook` | `sources/webhook.py` | Push-based: registers a POST endpoint per config entry, accepts arbitrary JSON (`title`, `description`/`message`/`text`, `url`), evaluates immediately |

### sources.yaml format

```yaml
sources:
  - type: rss
    name: BBC World News
    url: https://feeds.bbci.co.uk/news/world/rss.xml
    interval: 300        # polling interval in seconds

  - type: uptime_kuma
    name: Homelab Monitor
    url: http://uptime-kuma:3001
    slug: default        # status page slug
    interval: 60

  - type: webhook
    name: Custom Alerts
    path: /webhook/alerts  # POST endpoint exposed by PYTHIA
```

### Adding a new source

1. Create `backend/sources/my_source.py` extending `BaseSource`
2. Implement `fetch()` returning `List[RawEvent]`
3. Register the type in `SOURCE_REGISTRY` in `backend/sources/__init__.py`
4. Add an entry in `sources.yaml`

No modification to core files required.

---

## LLM Evaluation

### Behavior

The evaluator (`backend/evaluator.py`) sends each `RawEvent` to an OpenAI-compatible endpoint via `openai.AsyncOpenAI` and expects a strict JSON response. It is not a conversation — the LLM is used as a structured classification engine.

Key implementation details:
- **Streaming** (`stream=True`) to avoid timeouts on slow endpoints; chunks are accumulated then parsed
- `temperature=0.1`, `max_tokens=512`, 120s client timeout
- `_strip_thinking()` removes `<think>...</think>` blocks from reasoning models
- `_extract_json()` falls back to a regex `\{.*\}` match if direct parsing fails
- Up to 3 attempts (`retries=2`); returns `None` if all fail (event is dropped)
- Validates `criticality` ∈ [1, 10] and that the category matches the criticality range (mismatch → retry)
- Timestamp comes from `raw_data["published_at"]` when the source provides one, otherwise `now()` UTC

### System prompt

The system prompt (English and French variants, selected by `PYTHIA_LANGUAGE`) must:
- Instruct the model to return **only valid JSON**, no explanation, no markdown
- Define the exact output schema
- Define the categories and the criticality↔category mapping

### Output schema

```json
{
  "criticality": 7.4,
  "category": "DIVERGENCE",
  "title": "Short event title",
  "summary": "One or two sentence summary of the event.",
  "location": "Tokyo, Japan",
  "source": "BBC World News",
  "timestamp": "2025-02-25T14:32:00Z"
}
```

### Categories

| Category | Description |
|---|---|
| `NOMINAL` | Nothing unusual, low signal |
| `ELEVATED SCRUTINY` | Worth monitoring, not critical |
| `DIVERGENCE` | Significant unexpected event |
| `INTERVENTION IN PROGRESS` | Active incident or escalation |
| `CRITICAL DIVERGENCE` | Highest severity |

### Criticality scale

- `1–3` → NOMINAL
- `4–5` → ELEVATED SCRUTINY
- `6–7` → DIVERGENCE
- `8–9` → INTERVENTION IN PROGRESS
- `10` → CRITICAL DIVERGENCE

The category must always match the criticality range — the evaluator enforces this and retries on mismatch.

---

## Backend API

| Endpoint | Description |
|---|---|
| `GET /health` | `{"status": "ok", "connections": <int>}` — used by the Docker healthcheck |
| `GET /api/events` | Last 100 evaluated events (initial page load) |
| `GET /api/system` | Hardware metrics, per-source health, LLM provider/model (consumed by SystemPanel) |
| `WS /ws` | Persistent connection; replays history on connect, then broadcasts evaluated events |
| `POST /webhook/{path}` | One endpoint per `webhook` entry in `sources.yaml`, registered at startup |

The scheduler tracks per-source health (`source_health`) and applies exponential backoff on polling errors (capped at 1h).

---

## Frontend

### Visual states of PythiaCircle

PythiaCircle is a Canvas 2D geodesic sphere (Fibonacci node distribution, proximity mesh, dust shading, frost rim — no 3D library, hand-rolled projection in `requestAnimationFrame`). It reacts to incoming events based on criticality:

| State | Trigger | Visual |
|---|---|---|
| `idle` | No recent event | Slow spin, subtle shimmer |
| `analyzing` | Event received | Spin eases to a stop, local bulge ramps up at the emission angle |
| `divergence` | Evaluation displayed | Full-amplitude deformation + daggers, intensity scales with criticality |
| `returning` | After display duration | 3.5s decay back to idle |

Props contract: `state`, `criticality`, `queueSize`, `emissionAngle`, `onReturnComplete`.

### Display durations

Linear scale in `Display.jsx`: `(8 + (criticality − 1) × 3)` seconds — crit 1 → 8s, crit 5 → 20s, crit 10 → 35s.

If multiple events are queued, the pending queue is sorted by criticality (highest first).

### HUD & SystemPanel

- `HUDOverlay.jsx` — brand block, registration marks, analyzing indicator, nominal label, and the data block (timestamp, category, location, title, source · criticality) with a ring marker at the emission angle
- `SystemPanel.jsx` — polls `/api/system` every 5s: clock, CPU/RAM/disk bars, GPU and temperatures when available (Linux/Jetson), source health dots, LLM provider + model

### /feed view

- Chronological list, newest first (max 100, mirrors backend history)
- Each card shows: title, criticality badge, category, summary, source, location, timestamp
- Color coding by criticality range (neutral palette, monochrome preferred)
- No deletion, no interaction beyond reading
- Link to original source URL if available

---

## Configuration

### .env variables

See `.env.example` (kept in sync with `backend/config.py`):

```env
# LLM endpoint — OpenRouter (openrouter.ai) or any OpenAI-compatible server
LLM_URL=https://openrouter.ai/api/v1
LLM_MODEL=nvidia/nemotron-3-super-120b-a12b:free
LLM_API_KEY=                # required

# Display
PYTHIA_LANGUAGE=en          # "en" or "fr"
CRITICALITY_THRESHOLD=1     # Events below this score are discarded

# Server (host ports exposed by Docker)
BACKEND_PORT=8082
FRONTEND_PORT=8081

# Sources config path (inside container)
SOURCES_FILE=sources.yaml
```

`scripts/check-env.sh` validates a `.env` file against `.env.example` (empty default = required key).

### Language support

`PYTHIA_LANGUAGE` controls:
- The LLM system prompt language (so summaries are returned in the right language — category names stay in English)
- The HUD labels via i18n files (`VITE_LANGUAGE` is baked into the frontend at build time from `PYTHIA_LANGUAGE`)

To add a new language: create `frontend/src/i18n/de.js` and add the locale to the backend system prompt builder.

---

## Tests

```bash
# Backend (pytest + pytest-asyncio)
cd backend && python -m pytest tests/ -v

# Frontend (vitest)
cd frontend && npm test -- --run
```

CI (GitHub Actions, self-hosted runner) runs both suites, then deploys with `docker compose up --build -d` and smoke-tests `/health`, `/api/events`, and the frontend.

---

## Docker

The project must be fully runnable with:

```bash
docker compose up --build -d
```

Services:
- `pythia-backend` — FastAPI app (container port 8000, exposed as `BACKEND_PORT`, 256MB limit)
- `pythia-frontend` — Vite build served by nginx (exposed as `FRONTEND_PORT`, 64MB limit, waits for backend healthcheck)

`sources.yaml` is mounted read-only into the backend container — editing it only requires a backend restart, not a rebuild. The LLM runs remotely (or on the host); the backend reaches it via `LLM_URL`.

---

## Coding Conventions

- **Language**: all code, comments, commit messages, and documentation in **English**
- **Backend**: Python 3.11+, async everywhere, Pydantic models for all data structures
- **Frontend**: React functional components only, no class components
- **Styling**: CSS modules, no inline styles except for dynamic canvas values
- **Canvas**: all sphere animations live in `PythiaCircle.jsx` only, no animation logic elsewhere
- **WebSocket**: single connection managed by `useWebSocket.js` hook, consumed by both views
- **Config**: nothing hardcoded — all tunables go through `.env` or `sources.yaml`

---

## What NOT To Do

- **Do not** hardcode any LLM model name, URL, API key, or source URL anywhere in the code
- **Do not** put business logic inside React components — keep components visual only
- **Do not** store events in a database — the in-memory queue (deque, 100 events) is sufficient, keep it simple
- **Do not** make `/display` interactive — no click handlers, no hover states, no scrolling
- **Do not** make the LLM answer in free text — always enforce JSON output, reject and retry if parsing fails
- **Do not** mix animation state with application state — keep them in separate hooks or stores
- **Do not** add authentication — PYTHIA is a local network tool, not a public service
- **Do not** install heavy dependencies without a clear reason — keep the bundle lean
