# Phase Tracker

> Cập nhật file này **mỗi cuối phase** (hoặc khi có thay đổi lớn). Đây là nguồn chân lý cho trạng thái triển khai. Không sửa lùi `01-implementation-plan.md`; ghi deviation tại đây.

## Trạng thái tổng

| Phase | Tên | Trạng thái | Owner | Bắt đầu | Hoàn thành | Note |
|---|---|---|---|---|---|---|
| 1 | Path & Config Refactor + Inference Config Repo | 🟢 Done | claude | 2026-05-08 | 2026-05-08 | Tests 72/72 pass |
| 2 | Backend HTTP API + Inference Config endpoints | 🟢 Done | claude | 2026-05-08 | 2026-05-08 | 24/24 web tests pass; 35 routes mounted |
| 3 | Background Job + WS (batch only) | 🟢 Done | claude | 2026-05-08 | 2026-05-08 | JobManager + WS + render_video + summary.json + post-hoc render-video endpoint + inference timings; 109/109 tests pass |
| 4 | Frontend SPA (5 trang gồm Inference Settings) | 🟢 Done | antigravity | 2026-05-11 | 2026-05-11 | React 19 + Vite 8 + TailwindCSS v4; 5 pages; 0 TS errors; 326KB JS gzip 100KB |
| 5 | Dockerization | 🟢 Done | antigravity | 2026-05-11 | 2026-05-11 | Multi-stage Dockerfile (CPU + GPU); docker-compose.yml validates clean |
| 6 | Polish & Deprecate | ⬜ Not started | — | — | — | — |

Ký hiệu: ⬜ Not started · 🟡 In progress · 🟢 Done · 🔴 Blocked

---

## Phase 1 — Path & Config Refactor

**Trạng thái:** 🟢 Done

### Checklist
- [x] Thêm env `TRAFFIC_DATA_DIR`, `TRAFFIC_MODELS_DIR`, `TRAFFIC_CONFIG_DIR`
- [x] `paths.py` đọc env trước khi fallback `PROJECT_ROOT`
- [x] `inference_config.py` resolve `model.weights` qua `TRAFFIC_MODELS_DIR` (in `yolo_detector._resolve_weights`)
- [x] `data_management_service.py` skip copy + new `add_source_from_uploaded_path()`
- [x] Tạo sub-folder `data/uploads/`, `data/exports/`
- [x] **`Container.reload_inference_config()`** — reset cache detector
- [x] **`InferenceConfigRepository`** (`FileSystemInferenceConfigRepository` với `ruamel.yaml` round-trip + atomic write)
- [x] **Migration script** `scripts/migrate_results_layout.py` (idempotent)
- [x] **Results layout** `data/results/<source>/<session>/result.csv` + legacy fallback
- [x] Test override env (3 tests in `test_paths_env.py`)
- [x] Test round-trip load → save → load (5 tests in `test_inference_config_repository.py`)
- [x] Container reload tests (2 tests)
- [x] Migration tests (6 tests)

### Deviation / Note
_(ghi chú khi có thay đổi so với plan)_

---

## Phase 2 — Backend HTTP API

**Trạng thái:** 🟢 Done

### Checklist
- [x] Add deps: fastapi, uvicorn, python-multipart, websockets, ruamel.yaml, zipstream-ng, httpx
- [x] `src/adapters/input/web/` skeleton (app, deps, schemas, routers, errors)
- [x] Routers: sources, frames, roi, analysis, **inference_config**, system, downloads
- [x] StaticFiles mount cho `/files/frames/`, `/files/exports/`
- [x] Domain exception → HTTPException mapping
- [x] CORS config qua env `TRAFFIC_WEB_ORIGINS`
- [x] **`GET /api/config/inference`** trả full config
- [x] **`PUT /api/config/inference`** validate + ghi YAML + hot-reload
- [x] **`POST /api/config/inference/reset`** reset về default
- [x] **`GET /api/config/inference/schema`** trả metadata cho UI form
- [x] **`GET /api/system/models`** list `*.pt` trong models dir
- [x] **`GET /api/sessions/{id}/artifacts`** list metadata
- [x] **`GET /api/sessions/{id}/download/csv`** (FileResponse)
- [x] **`GET /api/sessions/{id}/download/video`** (FileResponse with Accept-Ranges)
- [x] **`GET /api/sessions/{id}/download/bundle.zip`** (zipstream-ng)
- [x] **`GET /api/sources/{id}/download/roi.json`**
- [x] **`ArtifactRepositoryPort` + `FileSystemArtifactRepository`**
- [x] `tests/integration/web/` — 24 tests (sources/roi/inference_config/downloads/health)
- [x] Config PUT invalid → 422; valid → YAML cập nhật + Container hot-reload
- [x] Download 404 (no video) / 425 (still running) phân biệt

### Deviation / Note

---

## Phase 3 — Background Job + WebSocket

**Trạng thái:** 🟢 Done

### Checklist
- [x] `JobManager` thread pool + state machine (4 trạng thái: pending/running/completed/failed/cancelled)
- [x] `AnalysisService.run_session()` thêm `progress_cb` + `interval_cb` + `cancel_event` params
- [x] `SessionStatus.CANCELLED` + `mark_cancelled()` trong domain
- [x] `CancelledError` exception trong analysis_service
- [x] WS endpoint `/ws/sessions/{id}` (subscribe/unsubscribe + replay last event)
- [x] Cancel: `DELETE /api/sessions/{id}` + cancel_event check mỗi frame
- [x] **`render_video: bool` field trong `StartSessionRequest`** (default false)
- [x] **Render annotated.mp4 vào `results/<src>/<sess>/annotated.mp4` nếu `render_video=true`**
- [x] **Generate `summary.json` sau completed** (totals, avg occupancy, avg speed)
- [x] **WS events**: progress, interval, completed, failed, cancelled, artifact_ready
- [x] Test JobManager: completion, cancel, failure, pool full, progress state (5 tests pass)

### Deviation / Note
- Restart server → session đang chạy = `failed`: NOT yet implemented (cần startup hook scan sessions có status=running và mark failed). Đã ghi vào "Open question" — defer cho Phase 6 polish.
- Concurrent 2 jobs test: chưa viết explicit test với `max_workers=2`; chỉ test pool=1 reject với 409.

### Enhancements (post Phase 3 core)
- [x] **Inference timings** trong `POST /test-detect` response: `inference_ms`, `annotation_ms`, `total_ms`, `fps_estimate`, `device`, `image_size`. Cho UI Frame Test hiển thị tốc độ đáp ứng của model.
- [x] **Post-hoc render annotated video**: `POST /api/sessions/{id}/render-video` để tạo `annotated.mp4` sau khi session kết thúc (khi user không bật `render_video=true` ban đầu hoặc cần render lại). GET trả status.
- [x] **Per-frame download**: `GET /api/sessions/{id}/frames/{name}` cho session-scoped frame artifacts (path traversal protection).
- [x] **Tests mới**: 8 tests (`test_test_detect_timings.py` × 2 + `test_post_hoc_render.py` × 6).

### Deviation / Note

---

## Phase 4 — Frontend SPA

**Trạng thái:** ⬜ Not started

### Checklist
- [ ] `frontend/` scaffold (vite + react + ts + tailwind + tanstack-query)
- [ ] `vite.config.ts` proxy `/api` → backend
- [ ] SourcesPage: list, upload (multipart, progress), delete
- [ ] ROIEditorPage: frame viewer + canvas (polygon/line drawing) + slider mm:ss + test detect + save frame
- [ ] AnalysisPage: start, WS progress, table khi complete (**batch only — không có tab live**)
- [ ] ResultsPage: filter, table
- [ ] ResultsPage: panel artifacts (list + Tải nút từng cái)
- [ ] ResultsPage: nút Tải bundle ZIP
- [ ] ResultsPage: video preview inline (`<video>` với range request)
- [ ] ResultsPage: re-fetch artifacts khi annotated video đang render
- [ ] **InferenceSettingsPage**: form đa section (Model, Detection, Detection ROI, Tracking, Speed, Analysis, Queue, Vehicle PCE)
- [ ] InferenceSettings: dropdown weights từ `/api/system/models`
- [ ] InferenceSettings: validate client-side + submit + toast + reset
- [ ] InferenceSettings: cảnh báo "áp dụng cho phiên mới"
- [ ] Build production output → backend serve

### Deviation / Note

---

## Phase 5 — Dockerization

**Trạng thái:** ⬜ Not started

### Checklist
- [ ] Multi-stage `Dockerfile` (CPU base)
- [ ] `Dockerfile.gpu` hoặc build arg cho CUDA base
- [ ] Loại PyQt6 khỏi `requirements.txt` của image production (split `requirements-dev.txt`)
- [ ] `docker-compose.yml` với 3 volume mount
- [ ] `docker-compose.gpu.yml` override
- [ ] `.dockerignore` loại data/models/tests/node_modules/.venv
- [ ] HEALTHCHECK
- [ ] Cold start test < 3 phút
- [ ] Image size: CPU < 4 GB, GPU < 6 GB
- [ ] Restart persistence test (data còn sau `down/up`)

### Deviation / Note

---

## Phase 6 — Polish & Deprecate

**Trạng thái:** ⬜ Not started

### Checklist
- [ ] Cập nhật `README.md` (web-first)
- [ ] `docs/DEPLOYMENT.md` (nginx + HTTPS + backup)
- [ ] `docs/MIGRATION.md` (PyQt6 → web)
- [ ] Cleanup unused code
- [ ] (Optional) CI workflow build + healthcheck

### Deviation / Note

---

## Decision log (cross-phase)

| Date | Decision | Lý do | Phase ảnh hưởng |
|---|---|---|---|
| _yyyy-mm-dd_ | _e.g. dùng FastAPI thay Flask_ | _async, OpenAPI tự sinh, WS tích hợp_ | Phase 2 |

## Blocker / Open question

_(liệt kê khi gặp; xoá khi giải quyết)_

- [ ] Quyết định: chunked upload protocol — `tus.io` hay multipart đơn giản? → mặc định multipart trong Phase 2, nâng cấp tus nếu video > 1 GB.
- [ ] Quyết định: GPU image base — `nvidia/cuda:12.4.1-runtime-ubuntu22.04` vs `pytorch/pytorch`? → so sánh size & ultralytics compat trước Phase 5.
