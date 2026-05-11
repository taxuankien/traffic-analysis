# Implementation Plan — Web Migration & Dockerization

> Tài liệu này mô tả **6 phase** chuyển đổi tuần tự. Mỗi phase có đầu vào, deliverables, kiểm tra hoàn thành (DoD = Definition of Done) rõ ràng. Tiến độ theo dõi tại [02-phase-tracker.md](02-phase-tracker.md).

## Tổng quan phase

| Phase | Tên | Thời lượng ước lượng | Tiền điều kiện |
|---|---|---|---|
| 1 | Path & Config Refactor (chuẩn bị Docker-friendly) | 1–2 ngày | Codebase hiện tại pass test |
| 2 | Backend HTTP API (FastAPI driving adapter) + **Inference Config endpoints** | 5–6 ngày | Phase 1 |
| 3 | Background job + WebSocket progress (batch only) | 2–3 ngày | Phase 2 |
| 4 | Frontend SPA (React + Vite) — 5 trang gồm **Inference Settings** | 6–8 ngày | Phase 2 (API stable) |
| 5 | Dockerization (image + compose + volume) | 2–3 ngày | Phase 4 |
| 6 | Polish, docs, deprecate PyQt6 | 2 ngày | Phase 5 |

> **Ghi chú phạm vi phân tích:** Toàn bộ kế hoạch chỉ xử lý **video file đã upload**. Không có kịch bản RTSP / webcam / streaming live ở bất kỳ phase nào. WebSocket trong Phase 3 phục vụ duy nhất việc báo progress của job batch.

---

## 🔵 Phase 1 — Path & Config Refactor

**Mục tiêu:** Loại bỏ phụ thuộc đường dẫn tuyệt đối project-relative để code chạy được trong container với mount-points tuỳ ý.

### Đầu vào
- Codebase hiện tại: [src/bootstrap/paths.py](../../src/bootstrap/paths.py), [src/bootstrap/container.py](../../src/bootstrap/container.py), [src/bootstrap/inference_config.py](../../src/bootstrap/inference_config.py).

### Việc cần làm
- [ ] Thêm biến môi trường:
  - `TRAFFIC_DATA_DIR` → mặc định `${PROJECT_ROOT}/data` (giữ tương thích local).
  - `TRAFFIC_MODELS_DIR` → mặc định `${PROJECT_ROOT}/models`.
  - `TRAFFIC_CONFIG_DIR` → mặc định `${PROJECT_ROOT}/config`.
  - `TRAFFIC_INFERENCE_CONFIG` → đường dẫn file `inference.yaml` (đã có sẵn, giữ).
- [ ] Sửa `paths.py`:
  - `DEFAULT_DATA_DIR`, `DEFAULT_MODELS_DIR`, `DEFAULT_CONFIG_DIR` đọc env trước, fallback `PROJECT_ROOT/...`.
  - Thêm helper `resolve_model_path(name) -> Path` neo theo `TRAFFIC_MODELS_DIR`.
- [ ] Sửa `inference_config.py` / `container.py`:
  - Khi `model.weights` là tên file (không phải path tuyệt đối), resolve qua `TRAFFIC_MODELS_DIR` thay vì cwd/PROJECT_ROOT.
  - YOLO Ultralytics auto-download cũng nên ghi vào `TRAFFIC_MODELS_DIR` (set `YOLO_CONFIG_DIR` hoặc tải explicit trước rồi truyền path).
- [ ] Sửa `data_management_service.py`:
  - Khi user "thêm nguồn", **không copy nữa** nếu nguồn nằm trong `TRAFFIC_DATA_DIR/uploads/`. Logic copy chỉ chạy cho CLI legacy (xem Phase 2 cho upload qua HTTP).
- [ ] Bổ sung sub-folder `data/uploads/` (web upload đích) và `data/exports/` (CSV export đích).
- [ ] **Tách Container DI cho phép hot-reload `InferenceConfig`:**
  - Thêm method `Container.reload_inference_config(new_config: InferenceConfig)` — reset cache `_detector` và áp config mới.
  - Mục tiêu: Phase 2 endpoint `PUT /api/config/inference` gọi method này sau khi ghi YAML.
  - Đảm bảo phiên phân tích đang chạy không bị ảnh hưởng (snapshot config tại thời điểm `analysis_service()` được gọi; reload chỉ áp cho session mới).
- [ ] Tạo `InferenceConfigRepository` (mới, output port `InferenceConfigRepositoryPort`):
  - `load() -> InferenceConfig` đọc từ `TRAFFIC_INFERENCE_CONFIG`.
  - `save(config: InferenceConfig) -> None` ghi YAML, giữ comment nếu có thể (dùng `ruamel.yaml` thay cho `pyyaml`) — fallback `pyyaml` thuần nếu mất comment chấp nhận được.
- [ ] Update CLI/GUI để smoke-test rằng đổi env vẫn chạy được:
  ```bash
  TRAFFIC_DATA_DIR=/tmp/trafdata TRAFFIC_MODELS_DIR=/tmp/trafmodels python -m src.adapters.input.cli.main_cli list-sources
  ```

### Definition of Done
- Existing `pytest tests/unit/ tests/integration/` vẫn pass.
- Thêm 2 test mới: override env path → service đọc/ghi đúng vị trí mới.
- `run.bat` và `python -m src.adapters.input.gui.app` không bị regress.
- **Không** tồn tại `Path(__file__).resolve().parents[N]` mới ngoài `paths.py`.

---

## 🔵 Phase 2 — Backend HTTP API (FastAPI)

**Mục tiêu:** Xây dựng adapter `src/adapters/input/web/` exposing toàn bộ use-case qua REST. Đây là driving adapter song song với CLI/GUI — không đụng vào application services.

### Đầu vào
- Phase 1 hoàn tất.
- Spec API tham khảo [03-architecture-and-api.md](03-architecture-and-api.md).

### Việc cần làm
- [ ] Thêm dependency: `fastapi`, `uvicorn[standard]`, `python-multipart`, `websockets`.
- [ ] Tạo cấu trúc:
  ```
  src/adapters/input/web/
  ├── app.py              # FastAPI factory + lifespan (Container DI)
  ├── deps.py             # Depends() helpers — inject Container, services
  ├── schemas/            # Pydantic models cho request/response
  │   ├── source.py
  │   ├── roi.py
  │   ├── analysis.py
  │   ├── inference_config.py    # [NEW]
  │   └── result.py
  ├── routers/
  │   ├── sources.py      # CRUD VideoSource + upload (chỉ video file)
  │   ├── frames.py       # extract frame, test detect
  │   ├── roi.py          # GET/PUT ROI config
  │   ├── analysis.py     # start/list sessions, results
  │   ├── inference_config.py    # [NEW] GET/PUT inference params
  │   └── system.py       # /health, /system/monitor, /system/models
  └── errors.py           # Domain exception → HTTPException mapping
  ```
- [ ] Endpoint chính (full spec → file 03):
  - `POST /api/sources` (multipart upload) / `GET /api/sources` / `DELETE /api/sources/{id}`
  - `GET /api/sources/{id}/frame?time=1.5` → trả PNG bytes
  - `POST /api/sources/{id}/test-detect` → JSON detections + URL annotated PNG
  - `GET|PUT /api/sources/{id}/roi`
  - `POST /api/sources/{id}/sessions` → bắt đầu analysis batch (trả `session_id`, status `pending`)
  - `GET /api/sessions/{id}` / `GET /api/sources/{id}/sessions`
  - `GET /api/sessions/{id}/intervals?start=...&end=...`
  - `GET /api/sessions/{id}/export.csv`
  - **[NEW]** `GET /api/config/inference` → trả toàn bộ `InferenceConfig` hiện tại (model/detection/tracking/speed/analysis/queue/vehicle_pce + `detection_roi`)
  - **[NEW]** `PUT /api/config/inference` → validate + ghi YAML + hot-reload Container
  - **[NEW]** `POST /api/config/inference/reset` → reset về default snapshot (giữ trong code)
  - **[NEW]** `GET /api/config/inference/schema` → trả metadata cho UI form (range, default, mô tả) — generate từ docstring/Pydantic Field
  - **[NEW]** `GET /api/system/models` → list file `*.pt` có trong `TRAFFIC_MODELS_DIR` (cho UI chọn weights)
  - `GET /api/system/monitor` → CPU/GPU snapshot
  - **[NEW — download artifacts]**
    - `GET /api/sessions/{id}/artifacts` → list artifact metadata (csv, annotated video, frames, roi, summary.json) với `name`, `kind`, `size_bytes`, `mtime`, `download_url`.
    - `GET /api/sessions/{id}/download/csv` → kết quả interval (như `export.csv` cũ).
    - `GET /api/sessions/{id}/download/video` → annotated video `.mp4` (StreamingResponse). Trả 404 nếu chưa render; 425 (Too Early) nếu session chưa `completed`.
    - `GET /api/sessions/{id}/download/bundle.zip` → bundle gồm `result.csv`, `annotated.mp4` (nếu có), `roi.json`, `summary.json`, `frames/*` đã save. Stream qua `zipfly` hoặc `zipstream-ng` để không buffer toàn bộ vào RAM.
    - `GET /api/sources/{id}/download/roi.json` → ROI config (tiện cho user backup riêng).
- [ ] **[NEW] Output port `ArtifactRepositoryPort`** (mới):
  - `list(source_id, session_id) -> list[Artifact]`
  - `path_for(source_id, session_id, kind) -> Path | None`
  - Implement `FileSystemArtifactRepository` đọc layout `data/results/<source_id>/<session_id>/...`.
- [ ] Dùng FastAPI `FileResponse` cho file nhỏ (CSV, JSON), `StreamingResponse` cho video lớn (server không load toàn bộ vào RAM). Đặt header `Content-Disposition: attachment; filename="..."`.
- [ ] Range request support cho video: dùng `StreamingResponse` với header `Accept-Ranges: bytes` để browser seek được khi preview.
- [ ] Static file serving: `/files/frames/...`, `/files/exports/...` mapping vào `TRAFFIC_DATA_DIR`. Dùng `StaticFiles` của FastAPI, nhưng giới hạn chỉ 2 sub-folder cho phép.
- [ ] Domain exception → HTTP code:
  - `FileNotFoundError`, `SourceNotFound` → 404
  - `ValueError`/`InvalidROI`/`InvalidInferenceConfig` → 400
  - Lỗi inference (model load, weights file không tồn tại) → 503
- [ ] Validation cho `PUT /api/config/inference`:
  - confidence ∈ [0, 1]; iou ∈ [0, 1]; imgsz là bội số 32 và ≥ 320; max_det ≥ 1
  - tracking thresholds ∈ [0, 1]; lost_track_buffer ≥ 1; minimum_consecutive_frames ≥ 1
  - frame_skip ∈ [1, 10] (cảnh báo nếu > 3 — tracker dễ vỡ, xem comment trong YAML)
  - vehicle_pce values ≥ 0
  - weights: nếu là tên file (không có `/`), phải tồn tại trong `TRAFFIC_MODELS_DIR`; nếu là path tuyệt đối, file phải tồn tại
  - device: chỉ chấp nhận `null` / `"cpu"` / `"cuda"` / `"cuda:N"` / `"mps"`
  - detection_roi.bounds ∈ [0, 1] và `x_min < x_max`, `y_min < y_max`
  - Reject với 400 + danh sách lỗi cụ thể nếu fail (không partial-save)
- [ ] CORS: chỉ cho phép origin từ env `TRAFFIC_WEB_ORIGINS` (mặc định `http://localhost:5173,http://localhost:8080`).
- [ ] Test integration: `pytest tests/integration/web/` — dùng `TestClient` của FastAPI, mock heavy services khi cần.

### Definition of Done
- `uvicorn src.adapters.input.web.app:create_app --factory --reload` chạy, `GET /api/sources` trả `[]`.
- Toàn bộ endpoint chạy được qua `curl` (script smoke test trong `tests/integration/web/smoke.sh`).
- Upload video 100 MB qua `POST /api/sources` thành công, file xuất hiện ở `data/uploads/`.
- `PUT /api/config/inference` ghi đúng vào YAML, `GET` ngay sau đó trả về giá trị mới, lần `analysis_service()` kế tiếp dùng config mới (verify qua test detector cache reset).
- Sửa giá trị invalid → 400, file YAML không thay đổi.
- Không có endpoint nào blocking quá 100ms (phân tích → Phase 3).

---

## 🔵 Phase 3 — Background Job + WebSocket Progress

**Mục tiêu:** `AnalysisService.run_session()` chạy trong worker, client nhận progress real-time qua WebSocket thay vì polling.

### Đầu vào
- Phase 2 hoàn tất.

### Việc cần làm
- [ ] Tạo `src/adapters/input/web/jobs.py`:
  - `JobManager` với thread pool (size = env `TRAFFIC_MAX_JOBS`, default 1 — phân tích nặng GPU).
  - State per job: `pending → running → completed/failed`, lưu in-memory + persist trạng thái cuối qua `SessionRepository`.
  - Progress callback hook: chạy detect/track loop sẽ emit `(processed_frames, total_frames, current_interval)` qua queue.
- [ ] WebSocket endpoint: `WS /ws/sessions/{session_id}` — client connect ngay sau khi `POST sessions` trả `session_id`.
- [ ] `AnalysisService.run_session()` cần nhận thêm tham số `progress_callback: Callable[[ProgressEvent], None] | None = None`. (Sửa nhỏ ở application layer; mặc định `None` — CLI/GUI cũ không bị ảnh hưởng.)
- [ ] Cancel job: `DELETE /api/sessions/{id}` → set cancel flag; analysis loop check flag mỗi N frame.
- [ ] **[NEW] Render annotated video tuỳ chọn:**
  - Body `POST /api/sources/{id}/sessions` thêm field `render_video: bool = false` (default off để tránh tăng đôi thời gian phân tích).
  - Khi true, sau khi analysis loop xong, gọi `VisualizationService.render_full(...)` (đã tồn tại trong CLI `render` command) lưu vào `data/results/<source_id>/<session_id>/annotated.mp4`.
  - Phát event WS `{"type":"artifact_ready","kind":"video","url":"..."}` khi render xong.
- [ ] **[NEW] Generate `summary.json`** sau khi `completed`: tổng số xe theo loại, occupancy trung bình, avg speed toàn session, tổng số interval, thời lượng — lưu cùng folder. Phát event WS `artifact_ready` cho `summary`.
- [ ] Test: chạy session ngắn (video 10s), socket nhận ≥1 progress event và 1 event `completed`.

### Definition of Done
- Test: 2 phiên đồng thời (config `TRAFFIC_MAX_JOBS=2`) chạy không deadlock, không sai số liệu.
- Restart server giữa session: trạng thái session = `failed` (đã lưu trong session repo); không còn job zombie.
- WebSocket disconnect không làm crash worker; reconnect resume từ trạng thái mới nhất.

---

## 🔵 Phase 4 — Frontend SPA (React + Vite)

**Mục tiêu:** Xây dựng SPA thay thế PyQt6 GUI, phủ đủ 4 màn hình.

### Đầu vào
- Phase 2+3 hoàn tất, API spec stable.
- UX tham khảo [04-frontend-ux.md](04-frontend-ux.md).

### Việc cần làm
- [ ] Setup `frontend/` (peer của `src/`):
  ```
  frontend/
  ├── package.json        # vite, react, react-router, tanstack-query, tailwindcss
  ├── vite.config.ts      # proxy /api → http://localhost:8000
  ├── src/
  │   ├── main.tsx
  │   ├── App.tsx         # Layout + Router
  │   ├── api/            # fetch wrappers, ws client
  │   ├── pages/
  │   │   ├── SourcesPage.tsx
  │   │   ├── ROIEditorPage.tsx
  │   │   ├── AnalysisPage.tsx
  │   │   ├── ResultsPage.tsx
  │   │   └── InferenceSettingsPage.tsx   # [NEW]
  │   ├── components/
  │   │   ├── ROICanvas.tsx        # vẽ polygon/line trên <canvas>
  │   │   ├── VideoUploader.tsx    # multipart upload + progress
  │   │   ├── FrameViewer.tsx      # ảnh + slider time-slice
  │   │   ├── ProgressLive.tsx     # subscribe WS
  │   │   └── ConfigForm/          # [NEW] form group cho inference config
  │   └── hooks/
  └── public/
  ```
- [ ] **SourcesPage** — list + upload + delete. Nút "Cấu hình ROI" / "Phân tích" / "Xem kết quả" chuyển trang.
- [ ] **ROIEditorPage** — frame viewer + canvas overlay + slider mm:ss + nút "Run Test Detection" + "Save Frame" (chi tiết tương tác → file 04).
- [ ] **AnalysisPage** — chọn interval, bấm Start, hiển thị progress qua WS, bảng intervals khi complete. **Chỉ batch trên video đã upload — không có tab "live".**
- [ ] **ResultsPage** — filter session/time, bảng + **panel "Tải kết quả"**:
  - Đọc `GET /api/sessions/{id}/artifacts`.
  - Mỗi artifact một dòng: tên + size + mtime + nút Tải (download trực tiếp qua link API).
  - Nút "Tải bundle ZIP" gọi `/api/sessions/{id}/download/bundle.zip` — browser tự download.
  - Annotated video có `<video>` preview inline (range request) ngoài link tải.
  - Trạng thái "Đang render..." nếu video chưa sẵn sàng (re-fetch artifacts mỗi 5s khi session vừa completed và `render_video=true`).
- [ ] **[NEW] InferenceSettingsPage** — form đa section (Model / Detection / Detection ROI / Tracking / Speed / Analysis / Queue / Vehicle PCE):
  - Đọc `GET /api/config/inference` + `GET /api/config/inference/schema` để dựng form (label, mô tả, min/max).
  - Mỗi field có inline help text lấy từ schema.
  - Section "Model" có dropdown weights load từ `GET /api/system/models`.
  - Section "Detection ROI" có visualization preview (vẽ rectangle lên frame mẫu của 1 source bất kỳ — optional, có thể defer).
  - Nút "Lưu" → `PUT /api/config/inference` → toast success + invalidate query. Validate client-side trước (UX) ngoài server.
  - Nút "Khôi phục mặc định" → `POST /api/config/inference/reset` (với confirm dialog).
  - Cảnh báo khi sửa: "Thay đổi sẽ áp dụng cho phiên phân tích bắt đầu **sau** lúc lưu. Phiên đang chạy không bị ảnh hưởng."
- [ ] Build production: `npm run build` → output `frontend/dist/` được FastAPI mount tại `/` (StaticFiles). Trong dev, Vite dev server proxy.
- [ ] Smoke test thủ công: full 4 luồng trên Chrome/Firefox.

### Definition of Done
- Toàn bộ **5 luồng** nghiệp vụ thực hiện được qua web, không cần mở terminal hay sửa file YAML thủ công.
- Sửa confidence/iou trong UI → bấm Lưu → bắt đầu phiên phân tích mới → kết quả phản ánh đúng tham số mới (verify qua test thủ công với 2 giá trị confidence khác biệt rõ rệt).
- SPA build không lỗi TypeScript, lighthouse score > 70 (PWA optional).
- Upload video 200 MB qua web hoàn tất < 30s trên LAN.

---

## 🔵 Phase 5 — Dockerization

**Mục tiêu:** Đóng gói image, định nghĩa volume mount, chạy được bằng `docker compose up`.

### Đầu vào
- Phase 4 hoàn tất.
- Spec Docker → [06-docker-deployment.md](06-docker-deployment.md).

### Việc cần làm
- [ ] Multi-stage `Dockerfile` (xem 06 để biết chi tiết):
  - Stage 1: `node:20-alpine` — build frontend → `dist/`.
  - Stage 2: `python:3.11-slim` (CPU) hoặc `nvidia/cuda:12.x-runtime` (GPU) — install deps, copy `src/` + `dist/`, expose 8000.
  - Loại bỏ `PyQt6` khỏi `requirements.txt` của image production (giữ trong dev requirements).
- [ ] `docker-compose.yml`:
  - 1 service `web` (= API + static SPA).
  - Volumes:
    - `./data:/app/data`
    - `./models:/app/models`
    - `./config:/app/config` (**RW** vì UI Inference Settings ghi vào `inference.yaml`)
  - Env: `TRAFFIC_DATA_DIR=/app/data`, `TRAFFIC_MODELS_DIR=/app/models`, `TRAFFIC_INFERENCE_CONFIG=/app/config/inference.yaml`.
  - Port: `8080:8000`.
- [ ] `docker-compose.gpu.yml` (override) — `runtime: nvidia` + `deploy.resources.reservations.devices`.
- [ ] `.dockerignore`: loại `data/`, `models/`, `__pycache__`, `tests/`, `.venv`, `frontend/node_modules`.
- [ ] HEALTHCHECK: `curl -f http://localhost:8000/health`.
- [ ] Verify: thử rm container, restart → state (sources.json, sessions, results) còn nguyên trên host volume.

### Definition of Done
- `docker compose up -d` thành công lần đầu (cold start) trong < 3 phút sau khi build.
- Truy cập `http://localhost:8080` chạy đủ workflow.
- `docker compose down` không xoá data trên host.
- Image size: CPU < 4 GB, GPU < 6 GB (đã loại weights và data).
- README có hướng dẫn copy `models/yolo11m.pt` vào host trước khi `up`.

---

## 🔵 Phase 6 — Polish, Docs, Deprecate

**Mục tiêu:** Hoàn thiện UX, viết hướng dẫn deploy, deprecate PyQt6.

### Việc cần làm
- [ ] Cập nhật `README.md` chính: thêm mục "Web / Docker" lên đầu, mục "Desktop GUI (legacy)" xuống dưới với cảnh báo deprecate.
- [ ] `docs/DEPLOYMENT.md`: hướng dẫn deploy production (reverse proxy nginx + HTTPS, log rotation, backup `data/`).
- [ ] `docs/MIGRATION.md`: hướng dẫn người dùng PyQt6 cũ chuyển sang web (giữ `data/` không đổi → mount thẳng).
- [ ] Cleanup: xoá unused code trong CLI nếu trùng web (giữ CLI cho automation).
- [ ] CI smoke (optional): GitHub Action build image, chạy `pytest`, healthcheck.

### Definition of Done
- Người mới clone repo, `docker compose up` đi thẳng đến web UI hoạt động (sau khi đặt sẵn weights).
- PyQt6 GUI có warning banner khi chạy: "GUI desktop sẽ ngừng hỗ trợ ở phiên bản X.Y; chuyển sang web."
- Không còn `TODO web-migration` trong code.

---

## Verification Plan tổng thể

| Loại | Phương pháp |
|---|---|
| Unit | `pytest tests/unit/` — domain + path resolver mới |
| Integration | `pytest tests/integration/` — API endpoints, job manager, WS |
| E2E thủ công | Smoke test 4 luồng qua web sau Phase 4 và lại sau Phase 5 (trong container) |
| Performance | Phân tích video 10 phút 1080p — đảm bảo không chậm hơn baseline desktop > 10% |
| Volume | Restart container 3 lần — data persist |

## Phụ thuộc giữa phase

```
Phase 1 ──→ Phase 2 ──→ Phase 3 ──┐
                  └──→ Phase 4 ───┴──→ Phase 5 ──→ Phase 6
```

Phase 3 và 4 có thể chạy **song song** sau khi Phase 2 stable (API contract khoá lại).
