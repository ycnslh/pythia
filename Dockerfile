# Single image: the Vite build is served by the FastAPI backend (one process, one port).

# ── Frontend build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS frontend

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Runtime ──────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Run as an unprivileged user; /data holds the persisted state (volume)
RUN useradd --system --uid 10001 --no-create-home pythia \
    && mkdir /data && chown pythia /data

WORKDIR /app

# Dependencies first (layer cache)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend /app/dist ./static

ENV DATA_DIR=/data \
    STATIC_DIR=/app/static \
    PYTHONUNBUFFERED=1

USER pythia
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
