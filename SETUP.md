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
| `BACKEND_PORT` | `8082` |
| `FRONTEND_PORT` | `8081` |
| `SOURCES_FILE` | `sources.yaml` |

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
# All containers healthy?
docker compose ps

# Backend health endpoint
curl http://localhost:8082/health
# Expected: {"status":"ok"}

# Events API
curl http://localhost:8082/api/events
# Expected: {"events":[...]}

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/
# Expected: 200
```

Open in a browser:
- Display: `http://<host>:8081/display`
- Feed: `http://<host>:8081/feed`

Watch the backend logs to confirm LLM evaluation fires on the next RSS poll:

```bash
docker compose logs -f pythia-backend
```

## 5. Changing the model

Update `LLM_MODEL` in the GitHub Environment, then push any commit to `main` to trigger a redeploy. No rebuild needed — only the backend restarts.

To change it without a push:

```bash
# Edit .env directly on the machine, then:
docker compose up -d --force-recreate pythia-backend
```

Any model available on OpenRouter works.

## 6. Updating PYTHIA

Updating is automatic on push to `main`. To update manually on the machine:

```bash
git pull
docker compose up --build -d
```

Containers with `restart: unless-stopped` come back automatically after a reboot.
