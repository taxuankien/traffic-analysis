# Data Source Workflow — Web-based vs Desktop

> Tài liệu này mô tả thay đổi nghiệp vụ ở luồng "thêm nguồn dữ liệu" và "cấu hình" để phù hợp môi trường web, trong đó browser và server có thể nằm trên 2 máy khác nhau.

## Vấn đề với mô hình desktop hiện tại

Trong PyQt6 GUI:
1. User mở `QFileDialog` → chọn file local trên máy mình.
2. `DataManagementService.add_source(name, path)` nhận **đường dẫn tuyệt đối local**.
3. Service kiểm tra path có nằm trong `data_dir` không; nếu không, **copy file** vào `data/sources/`.
4. Đường dẫn trong `sources.json` lưu là path local (host filesystem).

Mô hình này giả định:
- Browser/UI và backend chạy trên **cùng một máy**.
- Backend có thể đọc trực tiếp đường dẫn user chọn.

→ Khi web-based hoặc Docker, **giả định này hỏng**:
- Browser không có quyền đưa local path cho server.
- Server trong container không thấy được filesystem host (trừ những volume đã mount).

## Mô hình web-based mới

### Quy tắc 1: Mọi nguồn nằm trong `TRAFFIC_DATA_DIR`

Server **không bao giờ** đọc file ngoài `TRAFFIC_DATA_DIR`. Hai sub-folder canonical:

```
${TRAFFIC_DATA_DIR}/
├── uploads/                    # Video user upload qua web
│   └── <source_id>_<orig>.mp4
├── ingested/                   # Video đã được nhập vào hệ thống bằng cách khác (mount volume, copy thủ công, scan thư mục)
│   └── <source_id>_<orig>.mp4
├── sources/sources.json        # Registry (path luôn là path tuyệt đối trong container)
├── configs/<source_id>.json    # ROI config — endpoint download `roi.json`
├── frames/                     # Frame export (mỗi PNG có thể download riêng)
├── exports/                    # CSV export tạm (legacy, có thể bỏ sau khi luồng download mới ổn định)
└── results/<source_id>/
    ├── sessions.json
    └── <session_id>/                # [NEW] mỗi session 1 folder thay vì 1 CSV phẳng
        ├── result.csv               # interval rows
        ├── summary.json             # tổng hợp toàn session
        ├── annotated.mp4            # (optional) chỉ có khi POST sessions với render_video=true
        └── frames/                  # (optional) frame đã save liên quan session
```

> **Lưu ý migration layout results:** Hiện tại CSV phẳng `results/<source_id>/<session_id>.csv`. Mới: `results/<source_id>/<session_id>/result.csv`. Cần migration script cùng Phase 1 — đọc layout cũ, tạo folder, di chuyển file. Idempotent, log warning nếu folder đã tồn tại.

`uploads/` là đích cho HTTP upload; `ingested/` cho 2 chế độ admin (mục Quy tắc 3).

### Quy tắc 2: Đăng ký nguồn = Upload file

API duy nhất tạo source qua web là `POST /api/sources` (multipart). Server:

1. Sinh `source_id`.
2. Lưu file stream vào `${TRAFFIC_DATA_DIR}/uploads/{source_id}_{filename}`.
3. Đọc metadata video (`SVVideoReader` lấy fps, total_frames, resolution).
4. Lưu `VideoSource(path=<absolute path trong container>)` vào `sources.json`.
5. Trả response.

> **Service-layer change:** thêm method `add_source_from_uploaded_path(name, uploaded_path, original_name)` trong `DataManagementService` — không copy lại (file đã ở đúng chỗ). Method `add_source(name, path)` cũ giữ cho CLI legacy.

### Quy tắc 3: Hỗ trợ nguồn "ngoài luồng upload" (admin / Docker)

Có hai trường hợp người dùng không muốn upload qua web:
- File đã sẵn trên server / mount volume (`/app/data/ingested/foo.mp4`).
- File rất lớn (> 2 GB), upload HTTP không thực tế.

→ Cung cấp 2 entrypoint thay thế:

#### a) CLI ingest (tận dụng `main_cli.py`)

```bash
# Container đã chạy
docker compose exec web \
  python -m src.adapters.input.cli.main_cli add-source "Cam 1" /app/data/ingested/cam1.mp4
```

Path phải là path **trong container**. CLI `add-source` đã có sẵn — chỉ cần đảm bảo Phase 1 sửa `data_management_service` skip copy khi path nằm trong `${TRAFFIC_DATA_DIR}`.

#### b) Endpoint admin scan (optional, defer được)

`POST /api/sources/scan` body `{"path": "ingested/cam1.mp4", "name": "Cam 1"}`:
- Server resolve relative theo `TRAFFIC_DATA_DIR`.
- Reject nếu path escape data dir (path traversal check).
- Đăng ký giống upload nhưng không copy.

→ Phase 2: implement; Phase 4: thêm UI nếu cần (chưa cần MVP).

### Quy tắc 4: Xoá source

`DELETE /api/sources/{id}`:
- Xoá entry trong `sources.json`.
- **Optional flag** `?purge=true`: xoá luôn file ở `uploads/` và mọi `results/<id>/`. Mặc định không xoá file để tránh mất dữ liệu vô ý.
- UI hiện 2 nút trong confirm dialog: "Xoá entry" (giữ file) vs "Xoá kèm video & kết quả".

### Quy tắc 5: Path trong `sources.json` luôn tương đối `TRAFFIC_DATA_DIR`

**Đây là thay đổi lớn so với hiện tại** (đang lưu absolute path).

Lý do: nếu user đổi mount-point Docker (`/data → /mnt/storage/data`), absolute path cũ vô dụng. Lưu relative giúp portable.

```json
// sources.json (mới)
{
  "id": "src_abc",
  "name": "Cam 1",
  "path": "uploads/src_abc_cam1.mp4",
  "kind": "file",
  "created_at": "..."
}
```

Tại runtime, mọi service resolve qua `(data_dir / source.path).resolve()`. Cần migration script (Phase 1):
- Đọc `sources.json` cũ.
- Với mỗi entry: nếu absolute và nằm trong `data_dir` → convert sang relative.
- Nếu absolute và nằm ngoài data_dir → log warning, để user xử lý thủ công.

→ Bổ sung vào checklist Phase 1.

---

## Cấu hình hệ thống — thay đổi

### `inference.yaml`

Giữ nguyên format. Hai thay đổi:

**1. Resolution của `model.weights`:**

| Trường hợp | Hiện tại | Mới |
|---|---|---|
| `weights: "models/yolo11m.pt"` | Resolve qua `PROJECT_ROOT` | Resolve qua `TRAFFIC_MODELS_DIR` (default = `${PROJECT_ROOT}/models` cho local) |
| `weights: "yolo11m.pt"` (không có dir) | Ultralytics auto-download cwd | Auto-download vào `TRAFFIC_MODELS_DIR` |
| `weights: "/abs/path.pt"` | Pass-through | Pass-through (giữ) |

**2. File YAML giờ là read-write từ web:**

- UI "Inference Settings" (xem [04-frontend-ux.md](04-frontend-ux.md) Page 5) ghi trực tiếp vào file qua endpoint `PUT /api/config/inference`.
- Volume mount Docker đổi từ `:ro` sang RW (xem [06-docker-deployment.md](06-docker-deployment.md)).
- Backend dùng `ruamel.yaml` để giữ comment + structure khi save (fallback `pyyaml` nếu không khả thi).
- Atomic write (ghi `.tmp` → rename) tránh corrupt khi crash giữa lúc save.
- CLI cũ vẫn đọc được file này → tương thích ngược.

### Workflow cấu hình tham số mô hình (NEW — first-class)

Đây là luồng nghiệp vụ thứ 5 (ngang hàng với 4 luồng per-source). Khác biệt: cấu hình **toàn cục**, không gắn với source cụ thể.

**Use case flow:**

1. User mở `Inference Settings` từ TopBar (không cần chọn source).
2. UI fetch `GET /api/config/inference` + `GET /api/config/inference/schema` + `GET /api/system/models`.
3. UI dựng form đa section, prefill từ config hiện tại.
4. User chỉnh tham số (ví dụ tăng `confidence` từ 0.15 lên 0.25 cho video sáng rõ).
5. Validate client-side khi user nhập (red highlight nếu invalid).
6. Bấm Lưu → `PUT /api/config/inference` với full body.
7. Server validate + ghi atomic + `Container.reload_inference_config(new_cfg)`.
8. Lần `analysis_service()` kế tiếp dùng config mới. Phiên đang chạy (nếu có) **không bị ảnh hưởng** vì `AnalysisService` đã capture config qua DI tại thời điểm khởi tạo.

**Bảo vệ phiên đang chạy:** trong `Container.analysis_service()`, snapshot tham số tại thời điểm gọi → truyền vào constructor `AnalysisService`. Reload chỉ reset `_detector` cache; service đã instantiate giữ reference riêng. Đây là **invariant phải test** ở Phase 1.

**Ranh giới responsibility:**

| Layer | Responsibility |
|---|---|
| Frontend (Page 5) | UI form, validate UX, dirty guard |
| Web router `inference_config.py` | HTTP I/O, exception → status code |
| `InferenceConfigRepositoryPort` (mới) | Load/save YAML, atomic write, giữ comment |
| `Container.reload_inference_config()` | Hot-reload — reset detector cache |
| `InferenceConfig` (existing) | Dataclass POJO, không thay đổi |

### Per-source config override (optional)

Một số tham số inference (confidence, IoU, frame_skip) có thể cần khác nhau giữa các camera. Đề xuất Phase sau:
- `data/configs/<source_id>.json` mở rộng schema, thêm `inference_overrides` optional.
- `Container.detector_for_source(source_id)` build detector với override merge từ YAML default + per-source.
- UI: thêm tab "Inference" trong ROI editor.

→ Không thuộc 6 phase chính; ghi chú để cân nhắc sau.

---

## So sánh luồng "Thêm nguồn"

| Bước | Desktop (PyQt6) | Web (mới) |
|---|---|---|
| 1. Chọn file | `QFileDialog` local | `<input type=file>` trong browser |
| 2. Truyền | Path local string | Multipart upload bytes |
| 3. Server lưu | Copy nếu cần vào `data/sources/` | Stream thẳng vào `data/uploads/` |
| 4. Metadata | Đọc sau khi save | Đọc sau khi save (giống nhau) |
| 5. Path lưu trong sources.json | Absolute | **Relative theo `data_dir`** |
| 6. Xoá file vật lý | Chỉ xoá entry | Optional `?purge=true` |

---

## Migration script (Phase 1)

Pseudo-code:

```python
# scripts/migrate_sources_to_relative.py
def migrate(data_dir: Path):
    sources_file = data_dir / "sources" / "sources.json"
    if not sources_file.exists():
        return
    sources = json.loads(sources_file.read_text())
    for s in sources:
        p = Path(s["path"])
        if p.is_absolute():
            try:
                rel = p.relative_to(data_dir)
                s["path"] = str(rel).replace("\\", "/")
            except ValueError:
                print(f"WARN: source {s['id']} path {p} outside data_dir; keep absolute")
    sources_file.write_text(json.dumps(sources, indent=2))
```

Chạy 1 lần khi container/server upgrade. Idempotent — chạy lại không hỏng.
