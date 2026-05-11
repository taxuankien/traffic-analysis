# syntax=docker/dockerfile:1.6

# ── Stage 1: build frontend ──────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build      # → /build/dist

# ── Stage 2: backend runtime ─────────────────────────────
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TRAFFIC_DATA_DIR=/app/data \
    TRAFFIC_MODELS_DIR=/app/models \
    TRAFFIC_CONFIG_DIR=/app/config \
    TRAFFIC_INFERENCE_CONFIG=/app/config/inference.yaml \
    YOLO_CONFIG_DIR=/app/models/.ultralytics

# System deps cho OpenCV + ffmpeg (cv2 cần libGL)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
        ffmpeg curl tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (production-only — không có PyQt6)
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

# App code
COPY src/ ./src/
COPY config/ ./config/

# SPA dist từ stage 1
COPY --from=frontend-build /build/dist ./frontend/dist

# Pre-create mount points (sẽ được override bằng volume)
RUN mkdir -p /app/data /app/models /app/data/uploads \
             /app/data/sources /app/data/configs \
             /app/data/frames /app/data/exports /app/data/results

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "src.adapters.input.web.app:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
