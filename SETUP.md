# PYTHIA — Jetson Setup Guide

Step-by-step deployment guide for the Nvidia Jetson Orin Nano Super (8GB, ARM64).

---

## Prerequisites

- Jetson Orin Nano Super flashed with JetPack (Ubuntu 22.04 base)
- NVMe SSD recommended (swap + Docker images)
- Network access to pull Docker images and HuggingFace models
- SSH access or a connected keyboard/monitor

---

## 1. RAM Optimizations

The Jetson has 8GB of unified RAM shared between CPU and GPU. Free as much as possible before running PYTHIA + vLLM.

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

### 1.3 Add swap space

vLLM loads model weights into unified RAM. Swap acts as a safety net against OOM kills.

First, identify your disk layout:

```bash
lsblk -o NAME,SIZE,MOUNTPOINT,FSTYPE
df -h
```

Then create the swapfile. If the NVMe is your root disk (everything under `/`), use `/var/swap`. If the NVMe is mounted separately (e.g. `/data`, `/mnt/ssd`), prefer that path to keep swap off the root partition.

```bash
# Adjust SWAP_PATH to match your setup:
#   /var/swap        — NVMe is root disk
#   /data/swapfile   — NVMe mounted at /data
#   /mnt/ssd/swapfile — NVMe mounted at /mnt/ssd
SWAP_PATH=/var/swap

sudo fallocate -l 8G $SWAP_PATH
sudo chmod 600 $SWAP_PATH
sudo mkswap $SWAP_PATH
sudo swapon $SWAP_PATH

# Persist across reboots
echo "$SWAP_PATH none swap sw 0 0" | sudo tee -a /etc/fstab
```

Verify:
```bash
free -h
swapon --show
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

## 3. Install NVIDIA Container Runtime

vLLM runs inside Docker and needs GPU access via the NVIDIA Container Runtime.

```bash
sudo apt install nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify:
```bash
docker run --rm --runtime=nvidia ubuntu nvidia-smi
```

---

## 4. Deploy PYTHIA

### 4.1 Clone the repository

```bash
git clone https://github.com/your-org/pythia.git
cd pythia
```

### 4.2 Accept the model license

The model `mistralai/Ministral-3-3B-Reasoning-2512` is gated on HuggingFace.

1. Go to `huggingface.co/mistralai/Ministral-3-3B-Reasoning-2512` and accept the license
2. Generate a token at `huggingface.co/settings/tokens`

### 4.3 Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
LLM_URL=http://pythia-llm:8000
LLM_MODEL=mistralai/Ministral-3-3B-Reasoning-2512
HF_TOKEN=hf_your_token_here

# "en" or "fr" — baked into the frontend bundle at build time
PYTHIA_LANGUAGE=en

# Discard events below this criticality score (1 = keep everything)
CRITICALITY_THRESHOLD=1

# Exposed ports
BACKEND_PORT=8082
FRONTEND_PORT=8081
```

### 4.4 Configure sources

Edit `sources.yaml` to define your RSS feeds, Uptime Kuma instance, or webhook sources:

```yaml
sources:
  - type: rss
    name: BBC World News
    url: https://feeds.bbci.co.uk/news/world/rss.xml
    interval: 300
```

### 4.5 Build and start

```bash
docker compose up --build -d
```

The first start downloads the model (~2GB) — this can take several minutes depending on your connection. Subsequent starts use the `hf-cache` Docker volume and are fast.

Follow the vLLM startup:
```bash
docker compose logs -f pythia-llm
# Wait for: "Application startup complete"
```

Check that all containers are healthy:
```bash
docker compose ps
```

---

## 5. Verify the deployment

```bash
# vLLM — list loaded models
curl http://localhost:8080/v1/models

# Backend health
curl http://localhost:8082/health

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/display
```

Open in a browser:
- Feed: `http://<jetson-ip>:8081/feed`
- Display: `http://<jetson-ip>:8081/display`

---

## 6. Kiosk display (optional)

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

## 7. Changing the model

Edit `LLM_MODEL` in `.env` then restart the LLM container:

```bash
docker compose up -d --force-recreate pythia-llm
```

The new model is downloaded automatically on first start (if not already in the `hf-cache` volume). No rebuild needed.

---

## 8. Updating PYTHIA

```bash
git pull
docker compose up --build -d
```

Containers with `restart: unless-stopped` will come back automatically after a reboot — no manual action needed.
