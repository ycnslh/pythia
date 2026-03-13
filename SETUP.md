# PYTHIA — Jetson Setup Guide

Step-by-step deployment guide for the Nvidia Jetson Orin Nano Super (8GB, ARM64).

---

## Prerequisites

- Jetson Orin Nano Super flashed with JetPack (Ubuntu 22.04 base)
- NVMe SSD recommended (Docker images)
- Network access (internet required for OpenRouter API calls)
- SSH access or a connected keyboard/monitor

---

## 1. RAM Optimizations

The Jetson has 8GB of unified RAM. Free as much as possible before running PYTHIA.

### 1.1 Disable the desktop GUI (~800MB freed)

PYTHIA runs headlessly — the display view is a browser page, not a desktop app.

```bash
# Switch to multi-user (headless) target permanently
sudo systemctl set-default multi-user.target

# Apply immediately without rebooting
sudo systemctl isolate multi-user.target
```

To revert if needed:
```bash
sudo systemctl set-default graphical.target
```

### 1.2 Disable nvargus-daemon

The Jetson camera/ISP daemon. PYTHIA does not use any camera.

```bash
sudo systemctl disable nvargus-daemon --now
```

---

## 2. Install Docker

```bash
# Install Docker Engine (includes Compose plugin)
curl -fsSL https://get.docker.com | sh

# Add your user to the docker group
sudo usermod -aG docker $USER
newgrp docker

# Enable Docker on boot
sudo systemctl enable docker
```

---

## 3. Deploy PYTHIA

### 3.1 Clone the repository

```bash
git clone https://github.com/your-org/pythia.git
cd pythia
```

### 3.2 Get an OpenRouter API key

PYTHIA uses [OpenRouter](https://openrouter.ai) for LLM inference — no local GPU needed.

1. Create an account at `openrouter.ai`
2. Generate a key at `openrouter.ai/keys`

### 3.3 Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
LLM_URL=https://openrouter.ai/api/v1
LLM_MODEL=nvidia/nemotron-3-super-120b-a12b:free
LLM_API_KEY=sk-or-v1-your-key-here

# "en" or "fr" — baked into the frontend bundle at build time
PYTHIA_LANGUAGE=en

# Discard events below this criticality score (1 = keep everything)
CRITICALITY_THRESHOLD=1

# Exposed ports
BACKEND_PORT=8082
FRONTEND_PORT=8081
```

### 3.4 Configure sources

Edit `sources.yaml` to define your RSS feeds, Uptime Kuma instance, or webhook sources:

```yaml
sources:
  - type: rss
    name: BBC World News
    url: https://feeds.bbci.co.uk/news/world/rss.xml
    interval: 300
```

### 3.5 Build and start

```bash
docker compose up --build -d
```

Check that all containers are healthy:
```bash
docker compose ps
```

---

## 4. Verify the deployment

```bash
# Backend health
curl http://localhost:8082/health

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/display
```

Open in a browser:
- Feed: `http://<jetson-ip>:8081/feed`
- Display: `http://<jetson-ip>:8081/display`

---

## 5. Kiosk display (optional)

If you want the Jetson to drive a dedicated screen showing `/display` on boot, install Chromium and launch it in kiosk mode.

```bash
sudo apt install chromium-browser -y
```

Create a systemd user service at `~/.config/systemd/user/pythia-kiosk.service`:

```ini
[Unit]
Description=PYTHIA kiosk display
After=network-online.target

[Service]
Environment=DISPLAY=:0
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  http://localhost:8081/display
Restart=on-failure

[Install]
WantedBy=default.target
```

Enable:
```bash
systemctl --user enable pythia-kiosk
systemctl --user start pythia-kiosk
```

---

## 6. Changing the model

Edit `LLM_MODEL` in `.env`, then restart the backend:

```bash
docker compose up -d --force-recreate pythia-backend
```

Any model available on OpenRouter works — no rebuild needed.

---

## 7. Updating PYTHIA

```bash
git pull
docker compose up --build -d
```

Containers with `restart: unless-stopped` will come back automatically after a reboot — no manual action needed.
