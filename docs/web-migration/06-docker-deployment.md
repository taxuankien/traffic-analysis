# Docker Deployment

> Mục tiêu: đóng gói image cho production, mount `data/` và `models/` làm volume, hỗ trợ cả CPU và GPU.

## Cấu trúc mount

```
HOST                                CONTAINER
├── data/               ←→          /app/data         (RW)
├── models/             ←→          /app/models       (RW — Ultralytics có thể auto-download)
└── config/             ←→          /app/config       (RW — UI Inference Settings ghi inference.yaml)
```

- `/app/data`: RW. Container ghi sources, configs ROI, frames, exports, results.
- `/app/models`: RW. Lý do: Ultralytics có thể tự download weights khi user chọn weights chưa có local + cần ghi cache vào `.ultralytics/`. Có thể đổi RO sau khi đã preload đủ weights.
- `/app/config`: **RW** (đổi so với plan ban đầu). UI "Inference Settings" ghi trực tiếp vào `inference.yaml` qua `PUT /api/config/inference`. Backend dùng atomic write để tránh corrupt.

> **Mount thư mục thay vì mount file đơn lẻ** cho `config/`: Docker bind-mount file riêng có vấn đề với atomic rename (ghi `.tmp` rồi `rename` → break inode). Mount cả thư mục giải quyết.

## Biến môi trường

| Env | Default trong image | Mục đích |
|---|---|---|
| `TRAFFIC_DATA_DIR` | `/app/data` | Root cho mọi I/O |
| `TRAFFIC_MODELS_DIR` | `/app/models` | YOLO weights |
| `TRAFFIC_CONFIG_DIR` | `/app/config` | Cấu hình |
| `TRAFFIC_INFERENCE_CONFIG` | `/app/config/inference.yaml` | Path file YAML |
| `TRAFFIC_WEB_ORIGINS` | `*` (override khi deploy) | CORS allowlist |
| `TRAFFIC_MAX_JOBS` | `1` | Concurrent analysis |
| `UVICORN_WORKERS` | `1` | API worker count (giữ 1 vì state in-memory cho jobs) |
| `YOLO_CONFIG_DIR` | `/app/models/.ultralytics` | Cache Ultralytics |

## Dockerfile (CPU base)

```dockerfile
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
# requirements-prod.txt thêm ruamel.yaml (giữ comment khi UI lưu inference.yaml)
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
```

### `requirements-prod.txt` (split)

```
# Inference + web (no PyQt6)
ultralytics>=8.0
supervision>=0.25
numpy>=1.24
pandas>=2.0
opencv-python-headless>=4.9    # headless thay cho opencv-python — không cần GUI lib
pyyaml>=6.0
ruamel.yaml>=0.18              # giữ comment khi UI Inference Settings ghi YAML
psutil>=5.9
nvidia-ml-py>=12.0; platform_system != "Darwin"
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.9
websockets>=12.0
zipstream-ng>=1.7              # stream ZIP bundle download không buffer RAM
```

### `requirements-dev.txt` (cho local dev có PyQt6 + tests)

```
-r requirements-prod.txt
PyQt6>=6.6
pytest>=8.0
pytest-mock>=3.12
httpx>=0.27           # cho FastAPI TestClient
```

## Dockerfile.gpu (GPU variant)

```dockerfile
# syntax=docker/dockerfile:1.6

FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS runtime
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TRAFFIC_DATA_DIR=/app/data \
    TRAFFIC_MODELS_DIR=/app/models \
    TRAFFIC_CONFIG_DIR=/app/config \
    TRAFFIC_INFERENCE_CONFIG=/app/config/inference.yaml \
    YOLO_CONFIG_DIR=/app/models/.ultralytics

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
        libgl1 libglib2.0-0 ffmpeg curl tini \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.11 /usr/local/bin/python3

WORKDIR /app
COPY requirements-prod.txt ./
# Cài PyTorch CUDA build trước rồi mới cài ultralytics để tránh CPU wheel ghi đè
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu124 && \
    pip install --no-cache-dir -r requirements-prod.txt

COPY src/ ./src/
COPY config/ ./config/
COPY --from=frontend-build /build/dist ./frontend/dist

RUN mkdir -p /app/data /app/models

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "src.adapters.input.web.app:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

## docker-compose.yml

```yaml
services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    image: traffic-analysis:cpu
    container_name: traffic-analysis
    ports:
      - "8080:8000"
    volumes:
      - ./data:/app/data
      - ./models:/app/models
      - ./config:/app/config
    environment:
      TRAFFIC_WEB_ORIGINS: "http://localhost:8080"
      TRAFFIC_MAX_JOBS: "1"
    restart: unless-stopped
```

## docker-compose.gpu.yml (override)

```yaml
services:
  web:
    image: traffic-analysis:gpu
    build:
      dockerfile: Dockerfile.gpu
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

Chạy: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`.

## .dockerignore

```
.venv/
__pycache__/
*.pyc
.git/
.github/
.idea/
.vscode/
data/
models/
result/
tests/
docs/
frontend/node_modules/
frontend/dist/
*.log
.env*
README.md
implementation_plan.md
run.bat
```

> Lưu ý: `data/` và `models/` ignore để **không nhồi vào image**; chúng đến qua volume.

## Quy trình deploy lần đầu

```bash
# Trên host
git clone <repo>
cd traffic-analysis

# Đặt sẵn weights (optional — nếu không có, Ultralytics sẽ tải khi run đầu)
mkdir -p models
cp /path/to/yolo11m.pt models/

# Build image
docker compose build

# Chạy
docker compose up -d

# Mở browser
xdg-open http://localhost:8080
```

Verify:

```bash
curl -fsS http://localhost:8080/api/health
# {"status":"ok"}
```

## Persistence test

```bash
# 1. Add source qua web, chạy 1 phiên phân tích
# 2. Recreate container
docker compose down
docker compose up -d
# 3. Refresh browser → nguồn + kết quả vẫn còn (đọc từ ./data trên host)
```

## Update image

```bash
docker compose pull          # nếu image trên registry
# hoặc
git pull && docker compose build
docker compose up -d
```

`./data/` không bị ảnh hưởng vì là bind mount.

## Production checklist

- [ ] Đặt sau reverse proxy (nginx/Caddy) với HTTPS — direct expose port 8080 chỉ cho dev.
- [ ] `TRAFFIC_WEB_ORIGINS` whitelist domain thật.
- [ ] Backup `data/` **và `config/inference.yaml`** định kỳ — file YAML giờ có thể bị sửa qua web (`tar czf backup-$(date +%F).tgz data/ config/`).
- [ ] Limit upload size ở reverse proxy (`client_max_body_size 2g` trong nginx).
- [ ] Cấu hình nginx **proxy buffering off** cho endpoint download lớn để tránh đệm full file vào nginx tmp:
  ```nginx
  location ~ ^/api/sessions/[^/]+/download/ {
      proxy_buffering off;
      proxy_request_buffering off;
      proxy_pass http://backend;
      # giữ Range header
      proxy_set_header Range $http_range;
      proxy_set_header If-Range $http_if_range;
      proxy_read_timeout 1h;
      proxy_send_timeout 1h;
  }
  ```
- [ ] Log rotation: `docker logs` rotation hoặc forward sang syslog/loki.
- [ ] Resource limits: thêm `mem_limit`, `cpus` vào compose nếu chia sẻ host.
- [ ] Chạy non-root: thêm `USER appuser` trong Dockerfile + `chown` mount points (nếu host filesystem chấp nhận).

## Troubleshooting

| Triệu chứng | Khả năng | Cách xử |
|---|---|---|
| `cv2.imshow` lỗi trong container | dùng `opencv-python` thay headless | đổi sang `opencv-python-headless` (đã ghi trong requirements-prod) |
| YOLO download chậm/fail | network từ container ra ngoài bị chặn | đặt sẵn `models/yolo11m.pt` trên host |
| GPU không thấy | `nvidia-container-toolkit` chưa cài host | `nvidia-ctk runtime configure --runtime=docker && systemctl restart docker` |
| Permission denied khi ghi `data/` | uid container ≠ uid host owner | `chown -R 1000:1000 data/` hoặc bỏ `USER` trong Dockerfile |
| WebSocket disconnect qua nginx | proxy không pass `Upgrade` headers | thêm `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";` |
| Container OOM khi inference | imgsz quá cao + max_det cao | giảm `imgsz` hoặc đặt `mem_limit: 6g` |
