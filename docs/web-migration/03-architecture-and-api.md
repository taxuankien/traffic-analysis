# Architecture & API Specification

## Kiến trúc sau migration

```
┌─────────────────────────────────────────────────────────────────┐
│                     Browser (SPA — React)                        │
└───────────────┬─────────────────────────────────────┬───────────┘
                │ REST                                │ WebSocket
                │ /api/...                            │ /ws/sessions/{id}
                ▼                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FastAPI (driving adapter)                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  routers: sources, roi, frames, analysis, system         │   │
│  │  jobs.JobManager (thread pool) ──┐                       │   │
│  └──────────────────────────────────┼──────────────────────┘   │
│                                     │                            │
│                     Container DI ───┴──── (unchanged services)   │
└─────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Application Services (UNCHANGED)                │
│  AnalysisService │ ROIConfigService │ DataManagementService     │
│  FrameExtractionService │ VisualizationService                  │
└─────────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Driven Adapters (UNCHANGED)                    │
│  SVVideoReader │ YOLODetector │ SVByteTracker │ JSON/CSV repos  │
└─────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────┬──────────────────┬───────────────────────────┐
│  data/ (volume)  │ models/ (volume) │ config/inference.yaml (RO)│
└──────────────────┴──────────────────┴───────────────────────────┘
```

### Driving adapter mới

`src/adapters/input/web/` đứng cùng cấp với `cli/` và `gui/`. Tất cả router gọi service qua DI Container — không có business logic trong web layer.

```python
# src/adapters/input/web/app.py (skeleton)
def create_app() -> FastAPI:
    container = build_container_from_env()
    app = FastAPI(title="Traffic Analysis API", version="1.0")
    app.state.container = container
    app.state.jobs = JobManager(container, max_workers=int(os.getenv("TRAFFIC_MAX_JOBS", "1")))
    app.include_router(sources.router, prefix="/api")
    app.include_router(roi.router, prefix="/api")
    app.include_router(frames.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(inference_config.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(ws_router)  # /ws/sessions/{id}
    app.mount("/files", StaticFiles(directory=container.data_dir), name="files")
    if (frontend_dist := Path("/app/frontend/dist")).exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="spa")
    return app
```

---

## REST API Specification

> Base URL: `/api`. Tất cả request/response JSON trừ khi ghi rõ. Lỗi trả `{"detail": "..."}` (FastAPI default).

### Sources

#### `POST /api/sources` (multipart upload)
Upload video mới và đăng ký nguồn.

**Request** (`multipart/form-data`):
- `name: string` (form field)
- `file: binary` (form field)

**Response 201:**
```json
{
  "id": "src_abc123",
  "name": "Cam 1",
  "path": "/app/data/uploads/src_abc123_cam1.mp4",
  "kind": "file",
  "created_at": "2026-05-08T09:00:00Z",
  "metadata": { "fps": 30, "total_frames": 9000, "width": 1920, "height": 1080 }
}
```

**Notes:** Server lưu file vào `${TRAFFIC_DATA_DIR}/uploads/{source_id}_{filename}`. Không copy lại (thay đổi so với CLI cũ — xem [05-data-source-workflow.md](05-data-source-workflow.md)).

#### `GET /api/sources` → `[VideoSource]`
#### `GET /api/sources/{id}` → `VideoSource`
#### `DELETE /api/sources/{id}` → 204

---

### Frame extraction & test detect

#### `GET /api/sources/{id}/frame?time=1.5` (hoặc `?frame=45`)
Trả về PNG bytes của frame tại thời điểm/index chỉ định.

**Response:** `image/png` (raw bytes).

**Status:** 404 nếu source không có; 400 nếu time/frame ngoài khoảng.

#### `POST /api/sources/{id}/test-detect`
**Body:**
```json
{ "time": 1.5, "annotate": true }
```
**Response 200:**
```json
{
  "frame_index": 45,
  "detections": [
    { "class_id": 2, "class_name": "car", "confidence": 0.92, "bbox_xyxy": [x1,y1,x2,y2] }
  ],
  "summary": { "car": 5, "motorcycle": 12, "bus": 0, "truck": 1 },
  "annotated_url": "/files/frames/test_<source_id>_<idx>.png",
  "timings": {
    "inference_ms": 12.5,
    "annotation_ms": 1.2,
    "total_ms": 18.7,
    "fps_estimate": 80.0,
    "device": "cuda:0",
    "image_size": [1920, 1080]
  }
}
```

`timings` cho phép user đánh giá nhanh tốc độ đáp ứng của model trên hardware
hiện tại (sau khi đổi weights / imgsz / device qua UI Inference Settings) —
trước khi chạy phân tích batch dài. `fps_estimate = 1000 / inference_ms`
ước lượng số frame/giây model có thể xử lý (chưa tính tracker + zone +
disk I/O — thực tế batch luôn chậm hơn fps_estimate).

#### `POST /api/sources/{id}/frame/save`
**Body:** `{ "time": 1.5, "annotate": false }`
**Response:** `{ "url": "/files/frames/<source_id>_<frame_idx>.png" }`

---

### ROI Config

#### `GET /api/sources/{id}/roi` → `ROIConfig | null`
Trả `null` (200) nếu chưa cấu hình.

#### `PUT /api/sources/{id}/roi`
**Body:**
```json
{
  "reference_frame_index": 0,
  "roi_polygons": [
    {"name": "lane_1", "points": [[100,200],[400,200],[400,500],[100,500]]}
  ],
  "counting_lines": [
    {"name": "line_in", "start": [100,300], "end": [400,300], "direction": "in"}
  ],
  "pixels_per_meter": 12.5
}
```
**Response 200:** ROIConfig đã lưu (timestamps server-side).

---

### Inference Config (NEW — thay thế việc sửa `inference.yaml` thủ công)

#### `GET /api/config/inference` → `InferenceConfigDTO`

Trả về toàn bộ tham số hiện đang load. Mọi field map 1-1 với `config/inference.yaml`.

```json
{
  "model": {
    "weights": "models/yolo11m.pt",
    "device": null,
    "imgsz": 960,
    "half": false,
    "max_det": 1000,
    "agnostic_nms": false
  },
  "detection": {
    "confidence": 0.15,
    "iou": 0.4,
    "class_ids": [2, 3, 5, 7]
  },
  "detection_roi": {
    "enabled": false,
    "bounds": [0.0, 0.0, 1.0, 1.0]
  },
  "tracking": {
    "track_activation_threshold": 0.25,
    "lost_track_buffer": 30,
    "minimum_matching_threshold": 0.8,
    "minimum_consecutive_frames": 3
  },
  "speed": { "min_frames": 5 },
  "analysis": { "default_interval_seconds": 30.0, "frame_skip": 1 },
  "queue": { "stopped_speed_kmh": 5.0, "window_frames": 5 },
  "vehicle_pce": { "car": 1.0, "motorcycle": 0.25, "bus": 3.0, "truck": 2.5 }
}
```

#### `PUT /api/config/inference`

Body: cùng schema như GET response (full replacement). Server:

1. Validate (xem rules trong [01-implementation-plan.md](01-implementation-plan.md) Phase 2).
2. Ghi `TRAFFIC_INFERENCE_CONFIG` (atomic write: ghi tạm `.tmp` → rename).
3. `Container.reload_inference_config(new_cfg)` — reset cache detector.
4. Trả 200 với config đã lưu.

**Errors:**
- 400 `{"detail": [{"field": "model.imgsz", "msg": "must be multiple of 32"}, ...]}` — danh sách lỗi cụ thể.
- 503 nếu weights mới không load được (kiểm tra optional bằng dry-run YOLO load).

> Hot-reload chỉ áp cho phiên phân tích **bắt đầu sau** thời điểm PUT thành công. Phiên đang chạy giữ snapshot cũ — không restart.

#### `POST /api/config/inference/reset`

Reset về default snapshot (hardcoded trong `src/bootstrap/inference_config.py`). Trả 200 + config mặc định mới.

#### `GET /api/config/inference/schema` → metadata cho UI form

```json
{
  "model.weights": {
    "type": "string",
    "label": "YOLO weights",
    "description": "Path tới file .pt; tương đối project hoặc tuyệt đối.",
    "ui_hint": "model_picker"
  },
  "model.imgsz": {
    "type": "integer",
    "label": "Image size",
    "min": 320, "max": 1920, "step": 32,
    "default": 960,
    "description": "Kích thước ảnh inference (bội số 32). Tăng lên 1280/1920 cho video độ phân giải thấp / object nhỏ."
  },
  "detection.confidence": {
    "type": "number",
    "label": "Confidence threshold",
    "min": 0.0, "max": 1.0, "step": 0.01,
    "default": 0.15,
    "description": "Ngưỡng tin cậy tối thiểu. Giảm 0.15–0.20 cho video mờ / xe máy bị che."
  },
  "...": "..."
}
```

UI dùng metadata này để dựng form mà không cần hardcode field mỗi lần thêm.

#### `GET /api/system/models` → `[{name, size_mb, modified_at}]`

List file `*.pt` trong `TRAFFIC_MODELS_DIR` (non-recursive). Dùng cho dropdown weights trong UI.

```json
[
  { "name": "yolov8n.pt", "path": "models/yolov8n.pt", "size_mb": 6.2, "modified_at": "..." },
  { "name": "yolo11m.pt", "path": "models/yolo11m.pt", "size_mb": 38.7, "modified_at": "..." }
]
```

---

### Analysis sessions

> Mọi phiên phân tích là **batch trên video file đã upload**. Không có endpoint cho realtime/streaming/RTSP.

#### `POST /api/sources/{id}/sessions`
Bắt đầu phân tích batch; trả ngay `session_id`, công việc chạy nền cho đến khi xử lý hết video hoặc bị huỷ.

**Body:** `{ "interval_seconds": 30 }`
**Response 202:**
```json
{ "session_id": "sess_xyz", "status": "pending" }
```

**Errors:**
- 400 nếu chưa có ROI config (hệ thống yêu cầu).
- 409 nếu đã đạt `TRAFFIC_MAX_JOBS` đồng thời.

#### `GET /api/sources/{id}/sessions` → `[AnalysisSession]`

#### `GET /api/sessions/{id}` → `AnalysisSession`
```json
{
  "id": "sess_xyz",
  "source_id": "src_abc123",
  "status": "running",
  "progress": { "processed_frames": 1234, "total_frames": 9000, "current_interval": 5 },
  "started_at": "...", "completed_at": null
}
```

#### `DELETE /api/sessions/{id}` → 204
Set cancel flag; loop dừng ở frame check tiếp theo, status chuyển `cancelled`.

#### `GET /api/sessions/{id}/intervals?start=&end=` → `[AnalysisInterval]`

---

### Download Artifacts (NEW)

> Mọi artifact đều là **file thật trên `data/results/<source_id>/<session_id>/`**. Endpoint chỉ đọc file và stream về client. Không tính toán lại.

#### `GET /api/sessions/{id}/artifacts` → `[Artifact]`

List metadata các artifact có sẵn cho session. Dùng cho UI render danh sách "Tải kết quả".

```json
[
  {
    "kind": "csv",
    "name": "result.csv",
    "size_bytes": 12480,
    "mtime": "2026-05-08T10:14:32Z",
    "download_url": "/api/sessions/sess_xyz/download/csv"
  },
  {
    "kind": "video",
    "name": "annotated.mp4",
    "size_bytes": 215040000,
    "mtime": "2026-05-08T10:18:11Z",
    "download_url": "/api/sessions/sess_xyz/download/video",
    "preview_url": "/api/sessions/sess_xyz/download/video"
  },
  {
    "kind": "summary",
    "name": "summary.json",
    "size_bytes": 412,
    "mtime": "2026-05-08T10:14:33Z",
    "download_url": "/api/sessions/sess_xyz/download/summary"
  },
  {
    "kind": "roi",
    "name": "roi.json",
    "size_bytes": 220,
    "mtime": "2026-05-07T08:00:00Z",
    "download_url": "/api/sources/src_abc/download/roi.json"
  }
]
```

`kind` enum: `csv` · `video` · `summary` · `roi` · `frame` (cho mỗi PNG đã save) · `bundle` (virtual — chỉ trả từ link bundle).

Response thiếu artifact = artifact đó chưa tồn tại (ví dụ video chỉ có khi `render_video=true`).

#### `GET /api/sessions/{id}/download/csv`
**Response:** `text/csv` (`Content-Disposition: attachment; filename="<source>_<session>.csv"`).
Schema giống CSV hiện tại: `timestamp,duration_seconds,occupancy_ratio,avg_speed_kmh,bus,car,motorcycle,truck`.

#### `GET /api/sessions/{id}/download/video`
**Response:** `video/mp4` qua `StreamingResponse` với:
- `Accept-Ranges: bytes` (browser preview seek được)
- `Content-Length` (full size khi GET không kèm Range)
- 206 Partial Content khi có header `Range: bytes=N-M`
- `Content-Disposition: attachment; filename="annotated_<session>.mp4"` (khi user click Tải) hoặc `inline` (khi browser preview)

Status:
- 404 nếu file chưa tồn tại (session không bật `render_video`).
- 425 Too Early nếu session vẫn `running` / `pending` (video render sau khi loop xong).
- 200/206 khi sẵn sàng.

#### `GET /api/sessions/{id}/download/summary`
**Response:** `application/json`
```json
{
  "session_id": "sess_xyz",
  "source_id": "src_abc",
  "started_at": "...", "completed_at": "...",
  "duration_seconds": 600.0,
  "interval_count": 20,
  "totals": { "car": 245, "motorcycle": 1280, "bus": 12, "truck": 38 },
  "avg_occupancy_ratio": 0.31,
  "avg_speed_kmh": 27.4,
  "interval_seconds": 30.0
}
```

#### `GET /api/sources/{id}/download/roi.json`
**Response:** `application/json` — file `data/configs/<source_id>.json` raw.

#### `POST /api/sessions/{id}/render-video`

**Response 202:**
```json
{
  "session_id": "sess_xyz",
  "status": "running",
  "target": "/app/data/results/src_abc/sess_xyz/annotated.mp4",
  "download_url": "/api/sessions/sess_xyz/download/video"
}
```

Render annotated video sau khi session đã kết thúc. Dùng khi user không bật
`render_video=true` lúc start session, hoặc file annotated bị xoá thủ công.

**Status codes:**
- 202: render đã được schedule (hoặc đang chạy).
- 404: session không tồn tại.
- 409: session đang ở trạng thái không hợp lệ (e.g. `running` — chưa kết thúc).
- 503: JobManager chưa khởi động.

**Client flow:**
1. POST `/render-video` → 202.
2. Subscribe WS `/ws/sessions/{id}` để nhận `artifact_ready` event khi xong.
3. Hoặc poll `GET /api/sessions/{id}/render-video` → `{"status":"done","available":true}`.
4. GET `/download/video` để tải.

#### `GET /api/sessions/{id}/render-video`

Trả status render hiện tại + cờ `available` cho biết file đã sẵn sàng chưa.

```json
{ "session_id": "...", "status": "running|done|idle", "available": true }
```

#### `GET /api/sessions/{id}/frames/{frame_name}`

Tải 1 file PNG nằm trong `results/<source>/<session>/frames/`. Tên file phải
không chứa `..` / `/` / `\` (path traversal protection).

#### `GET /api/sessions/{id}/download/bundle.zip`
**Response:** `application/zip` qua `zipstream-ng` (không buffer toàn bộ vào RAM).

Cấu trúc ZIP:
```
<source_name>_<session_id>/
├── result.csv
├── summary.json
├── roi.json
├── annotated.mp4          (nếu có)
└── frames/                (nếu có frames đã save cho session)
    ├── frame_0030.png
    └── ...
```

Header: `Content-Disposition: attachment; filename="<source>_<session>_bundle.zip"`. Status 425 nếu session chưa completed.

#### Backward compat: `GET /api/sessions/{id}/export.csv`

Giữ alias cũ → redirect 308 sang `/api/sessions/{id}/download/csv`. Tránh break client cũ trong giai đoạn migration.

---

#### `GET /api/sessions/{id}/export.csv`
**Response:** `text/csv` — alias của `/api/sessions/{id}/download/csv` (xem trên).

---

### System

#### `GET /api/health` → `{"status": "ok"}`
#### `GET /api/system/monitor`
```json
{ "cpu_percent": 45.2, "ram_percent": 62.1, "gpu": [{"name": "RTX 4060", "util_percent": 78, "mem_used_mb": 4500, "mem_total_mb": 8192}] }
```

---

## WebSocket Protocol

### `WS /ws/sessions/{session_id}`

Client connect ngay sau `POST /api/sources/{id}/sessions` để nhận progress.

**Server → Client messages** (JSON, mỗi line một event):

```json
{ "type": "progress", "processed_frames": 1234, "total_frames": 9000, "current_interval": 5 }
{ "type": "interval", "data": { "timestamp": "...", "vehicle_counts": {...}, "occupancy_ratio": 0.35, "avg_speed_kmh": 28.5 } }
{ "type": "completed", "session_id": "sess_xyz" }
{ "type": "failed", "session_id": "sess_xyz", "error": "..." }
{ "type": "cancelled", "session_id": "sess_xyz" }
{ "type": "artifact_ready", "kind": "csv|video|summary", "url": "/api/sessions/sess_xyz/download/<kind>" }
```

`artifact_ready` phát theo thứ tự:
1. `summary` + `csv` ngay sau frame loop kết thúc thành công.
2. `video` sau khi `VisualizationService.render_full()` hoàn tất (chỉ khi `render_video=true`). Có thể đến **sau** event `completed` nếu render mất nhiều thời gian.

UI dùng event này để bật/tải artifact mà không cần poll `/artifacts`.

**Client → Server:** không có message (one-way).

**Reconnect strategy:** client reconnect tự động; server replay event cuối cùng (không phải toàn bộ lịch sử) khi nhận connect mới — đủ để UI cập nhật trạng thái.

**Throttle:** progress event tối đa 2 Hz để giảm tải; interval event gửi đầy đủ.

---

## Pydantic schemas (rút gọn)

```python
# schemas/source.py
class VideoSourceMetadata(BaseModel):
    fps: float
    total_frames: int
    width: int
    height: int

class VideoSourceResponse(BaseModel):
    id: str
    name: str
    path: str
    kind: Literal["file"]
    created_at: datetime
    metadata: VideoSourceMetadata | None = None

# schemas/roi.py
class Point(BaseModel):
    __root__: tuple[int, int]

class ROIPolygonDTO(BaseModel):
    name: str
    points: list[tuple[int, int]]

class CountingLineDTO(BaseModel):
    name: str
    start: tuple[int, int]
    end: tuple[int, int]
    direction: Literal["in", "out", "both"]

class ROIConfigDTO(BaseModel):
    reference_frame_index: int = 0
    roi_polygons: list[ROIPolygonDTO]
    counting_lines: list[CountingLineDTO]
    pixels_per_meter: float | None = None

# schemas/analysis.py
class StartSessionRequest(BaseModel):
    interval_seconds: float = 30.0

class SessionProgress(BaseModel):
    processed_frames: int
    total_frames: int
    current_interval: int

class AnalysisSessionResponse(BaseModel):
    id: str
    source_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    progress: SessionProgress | None = None
    started_at: datetime
    completed_at: datetime | None = None

# schemas/inference_config.py
class ModelSection(BaseModel):
    weights: str
    device: str | None = None  # None | "cpu" | "cuda" | "cuda:N" | "mps"
    imgsz: int = Field(960, ge=320, le=1920, multiple_of=32)
    half: bool = False
    max_det: int = Field(1000, ge=1)
    agnostic_nms: bool = False

class DetectionSection(BaseModel):
    confidence: float = Field(0.15, ge=0.0, le=1.0)
    iou: float = Field(0.4, ge=0.0, le=1.0)
    class_ids: list[int]

class DetectionROISection(BaseModel):
    enabled: bool = False
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

class TrackingSection(BaseModel):
    track_activation_threshold: float = Field(0.25, ge=0.0, le=1.0)
    lost_track_buffer: int = Field(30, ge=1)
    minimum_matching_threshold: float = Field(0.8, ge=0.0, le=1.0)
    minimum_consecutive_frames: int = Field(3, ge=1)

class SpeedSection(BaseModel):
    min_frames: int = Field(5, ge=1)

class AnalysisSection(BaseModel):
    default_interval_seconds: float = Field(30.0, gt=0)
    frame_skip: int = Field(1, ge=1, le=10)

class QueueSection(BaseModel):
    stopped_speed_kmh: float = Field(5.0, ge=0)
    window_frames: int = Field(5, ge=1)

class InferenceConfigDTO(BaseModel):
    model: ModelSection
    detection: DetectionSection
    detection_roi: DetectionROISection
    tracking: TrackingSection
    speed: SpeedSection
    analysis: AnalysisSection
    queue: QueueSection
    vehicle_pce: dict[str, float]   # name → PCE; values >= 0
```

---

## OpenAPI

FastAPI auto-generate OpenAPI 3.x tại `/openapi.json` và Swagger UI tại `/docs`. Frontend có thể dùng `openapi-typescript` để generate client types — khuyến nghị bật trong Phase 4 để giảm drift.
