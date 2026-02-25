# PYTHIA

> Divergence monitoring ambient display powered by a local LLM.
> Inspired by the Rehoboam system from Westworld.

---

## Project Overview

PYTHIA is an autonomous divergence monitoring system. It continuously ingests events from multiple configurable sources (RSS feeds, Uptime Kuma, webhooks, and more), evaluates their criticality using a local LLM via Ollama, and displays the result as an ambient visual interface.

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
Evaluator (Ollama / local LLM)
→ Returns structured JSON: { criticality, category, title, summary, location, source, timestamp }
      │
      ▼
Event Queue (in-memory, Redis-ready)
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
│   ├── main.py               # FastAPI app, WebSocket, routes
│   ├── evaluator.py          # LLM prompt + response parsing
│   ├── event_queue.py        # In-memory queue + WebSocket broadcast
│   ├── scheduler.py          # Polling loop for pull-based sources
│   ├── config.py             # Settings loaded from .env + sources.yaml
│   └── sources/
│       ├── base.py           # Abstract BaseSource class
│       ├── rss.py            # RSSSource
│       ├── uptime_kuma.py    # UptimeKumaSource
│       └── webhook.py        # WebhookSource (FastAPI router)
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Display.jsx   # /display — ambient fullscreen view
│   │   │   └── Feed.jsx      # /feed — event log view
│   │   ├── components/
│   │   │   ├── PythiaCircle.jsx   # Canvas 2D animated circle
│   │   │   └── HUDOverlay.jsx     # HUD text layer
│   │   ├── hooks/
│   │   │   └── useWebSocket.js    # WebSocket connection + event handling
│   │   ├── i18n/
│   │   │   ├── en.js
│   │   │   └── fr.js
│   │   └── App.jsx
│   ├── index.html
│   └── vite.config.js
├── sources.yaml              # Source definitions
├── .env                      # Local environment variables (gitignored)
├── .env.example              # Documented example (committed)
├── docker-compose.yml
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

    def get_type(self) -> str:
        raise NotImplementedError
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

### sources.yaml format

```yaml
sources:
  - type: rss
    name: BBC World News
    url: https://feeds.bbci.co.uk/news/world/rss.xml
    interval: 300        # polling interval in seconds

  - type: rss
    name: Le Monde
    url: https://feeds.lemonde.fr/rss/une.xml
    interval: 300

  - type: uptime_kuma
    name: Homelab Monitor
    url: http://uptime-kuma:3001
    api_key: YOUR_API_KEY
    interval: 60

  - type: webhook
    name: Custom Alerts
    path: /webhook/alerts  # POST endpoint exposed by PYTHIA
```

### Adding a new source

1. Create `backend/sources/my_source.py` extending `BaseSource`
2. Implement `fetch()` returning `List[RawEvent]`
3. Register the type in `config.py` source factory
4. Add an entry in `sources.yaml`

No modification to core files required.

---

## LLM Evaluation

### Behavior

The evaluator sends each `RawEvent` to Ollama and expects a strict JSON response. It is not a conversation — the LLM is used as a structured classification engine.

### System prompt

The system prompt must:
- Be written in the language defined by `PYTHIA_LANGUAGE`
- Instruct the model to return **only valid JSON**, no explanation, no markdown
- Define the exact output schema
- Define the categories

### Output schema

```json
{
  "criticality": 7.4,
  "category": "ELEVATED SCRUTINY",
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

The category must always match the criticality range.

---

## Frontend

### Visual states of PythiaCircle

The circle reacts to incoming events based on criticality:

| State | Trigger | Visual |
|---|---|---|
| `IDLE` | No recent event | Clean circle, slow subtle pulse |
| `ANALYZING` | Event received, LLM evaluating | Ink spread distortion begins |
| `DIVERGENCE` | Response received | Particle explosion, intensity = criticality / 10 |
| `RETURNING` | After display duration | Circle slowly returns to IDLE |

### HUD labels (i18n keys)

```js
// en.js
export default {
  systemName: "PYTHIA",
  subtitle: "DIVERGENCE ANALYSIS",
  criticality: "CRITICALITY",
  category: "CATEGORY",
  focalPoint: "FOCAL POINT",
  source: "SOURCE",
  analyzing: "ANALYZING...",
  nominal: "ALL SYSTEMS NOMINAL",
}
```

### Display durations

Each event stays on `/display` for a duration proportional to its criticality:
- Criticality 1–3: 10 seconds
- Criticality 4–6: 20 seconds
- Criticality 7–10: 30 seconds

If multiple events are queued, the highest criticality takes priority.

### /feed view

- Chronological list, newest first
- Each card shows: title, criticality badge, category, summary, source, timestamp
- Color coding by criticality range (neutral palette, monochrome preferred)
- No deletion, no interaction beyond reading
- Link to original source URL if available

---

## Configuration

### .env variables

```env
# Ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=Jadio/Qwen3_4b_instruct_q4km

# Display
PYTHIA_LANGUAGE=en          # "en" or "fr"
CRITICALITY_THRESHOLD=1     # Events below this score are discarded

# Server
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Optional
NEWS_API_KEY=               # For future NewsAPI source
```

### Language support

`PYTHIA_LANGUAGE` controls:
- The LLM system prompt language (so categories and summaries are returned in the right language)
- The HUD labels via i18n files
- The feed UI labels

To add a new language: create `frontend/src/i18n/de.js` and add the locale to the backend system prompt builder.

---

## Docker

The project must be fully runnable with:

```bash
docker-compose up
```

Services:
- `pythia-backend` — FastAPI app
- `pythia-frontend` — Vite build served by nginx

Ollama runs on the host machine (or Jetson), not inside Docker. The backend connects to it via `OLLAMA_URL`.

---

## Coding Conventions

- **Language**: all code, comments, commit messages, and documentation in **English**
- **Backend**: Python 3.11+, async everywhere, Pydantic models for all data structures
- **Frontend**: React functional components only, no class components
- **Styling**: CSS modules or Tailwind, no inline styles except for dynamic canvas values
- **Canvas**: all circle animations live in `PythiaCircle.jsx` only, no animation logic elsewhere
- **WebSocket**: single connection managed by `useWebSocket.js` hook, consumed by both views
- **Config**: nothing hardcoded — all tunables go through `.env` or `sources.yaml`
- **Imports**: absolute imports from `src/` in frontend

---

## What NOT To Do

- **Do not** hardcode any Ollama model name, URL, or source URL anywhere in the code
- **Do not** put business logic inside React components — keep components visual only
- **Do not** store events in a database for now — in-memory queue is sufficient, keep it simple
- **Do not** make `/display` interactive — no click handlers, no hover states, no scrolling
- **Do not** make the LLM answer in free text — always enforce JSON output, reject and retry if parsing fails
- **Do not** mix animation state with application state — keep them in separate hooks or stores
- **Do not** add authentication — PYTHIA is a local network tool, not a public service
- **Do not** install heavy dependencies without a clear reason — keep the bundle lean
