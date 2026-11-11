# PYTHIA — Setup Guide

## 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
sudo systemctl enable docker
```

## 2. Configure GitHub Environment

In your GitHub repository: **Settings → Environments → New environment** → name it `production`.

Add the following **variables** (`vars`):

| Variable | Example value |
|---|---|
| `LLM_URL` | `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | `nvidia/nemotron-3-super-120b-a12b:free` |
| `PYTHIA_LANGUAGE` | `en` |
| `CRITICALITY_THRESHOLD` | `1` |
| `DISPLAY_THRESHOLD` | `4` |
| `PYTHIA_PORT` | `8081` |
| `SOURCES_FILE` | `sources.yaml` |

`DISPLAY_QUEUE_MAX` (default `10`), `DISPLAY_MAX_AGE_S` (default `600`) and `LLM_CONCURRENCY` (default `2`) are optional. If you already had `FRONTEND_PORT` set, the deploy keeps using it as the port until you define `PYTHIA_PORT`; `BACKEND_PORT` is no longer used.

Add the following **secret**:

| Secret | Description |
|---|---|
| `LLM_API_KEY` | Your OpenRouter API key (generate at `openrouter.ai/keys`) |

## 3. Configure sources

Clone the repository on the target machine and edit `sources.yaml`:

```bash
git clone https://github.com/your-org/pythia.git
cd pythia
nano sources.yaml
```

Example:

```yaml
sources:
  - type: rss
    name: BBC World News
    url: https://feeds.bbci.co.uk/news/world/rss.xml
    interval: 300
```

## 4. Verify the deployment

After the first push to `main`, confirm everything is running:

```bash
# .env complete? (validates against .env.example)
bash scripts/check-env.sh

# Container healthy?
docker compose ps

# Health endpoint ("llm" is null until the first evaluation, then true/false)
curl http://localhost:8081/health
# Expected: {"status":"ok","connections":0,"llm":null}

# Events API
curl http://localhost:8081/api/events
# Expected: {"events":[...]}

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/
# Expected: 200

# Webhook (only if a `webhook` source is configured in sources.yaml)
curl -X POST http://localhost:8081/webhook/alerts -H 'content-type: application/json' -d '{"title":"Test"}'
# Expected: {"status":"accepted"}
```

Open in a browser:
- Display: `http://<host>:8081/display`
- Feed: `http://<host>:8081/feed`

Watch the backend logs to confirm LLM evaluation fires on the next RSS poll:

```bash
docker compose logs -f pythia
```

## 5. Changing the model

Update `LLM_MODEL` in the GitHub Environment, then push any commit to `main` to trigger a redeploy.

To change it without a push:

```bash
# Edit .env directly on the machine, then:
docker compose up -d --force-recreate pythia
```

Any model available on OpenRouter works — or any other OpenAI-compatible endpoint by changing `LLM_URL` as well. Pick a model that follows JSON-output instructions reliably; the evaluator rejects and retries malformed responses.

## 6. Updating PYTHIA

Updating is automatic on push to `main`. To update manually on the machine:

```bash
git pull
docker compose up --build -d
```

The container has `restart: unless-stopped` and comes back automatically after a reboot. Event history lives in the `pythia-data` volume: it survives updates. To start from a clean slate, run `docker compose down -v` (this deletes the volume).
