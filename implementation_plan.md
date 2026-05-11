# Kế Hoạch Xây Dựng Hệ Thống Phân Tích Giao Thông Dựa Trên Video

## Tổng Quan

Hệ thống phân tích dữ liệu giao thông từ nguồn video (file mp4/avi), cung cấp các chức năng:
- **Cấu hình ROI**: Trích xuất khung hình, vẽ line/vùng ROI + hiệu chuẩn camera (pixels/mét)
- **Phân tích giao thông (batch)**: Đếm xe theo loại, độ chiếm dụng không gian, vận tốc trung bình
- **Quản lý dữ liệu**: Lưu trữ và truy xuất kết quả phân tích theo từng nguồn dữ liệu

**Ràng buộc đã xác nhận:**

| Câu hỏi | Quyết định |
|---|---|
| Nguồn video | File video (mp4, avi) — không cần RTSP/webcam |
| Giao diện | Desktop GUI (PyQt6) |
| Model detection | YOLOv8 pre-trained COCO |
| Tính vận tốc | Cần hiệu chuẩn camera — tham số `pixels_per_meter` nhập trong luồng cấu hình |
| Xử lý | Batch — phân tích file sau khi quay |

Kiến trúc: **Hexagonal Architecture (Ports & Adapters)** — tách biệt domain logic khỏi adapter cụ thể, dễ bảo trì và nâng cấp.

---

## Kiến Trúc Hexagonal

```
┌─────────────────────────────────────────────────────────────┐
│                    DRIVING ADAPTERS (Input)                  │
│          CLI │ Desktop GUI │ Web API │ Scheduler             │
└───────────────────────┬─────────────────────────────────────┘
                        │ Input Ports
┌───────────────────────▼─────────────────────────────────────┐
│                      APPLICATION CORE                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Use Cases / Services                    │    │
│  │  ROIConfigService │ AnalysisService │ DataService    │    │
│  └──────────────┬─────────────────────────┬────────────┘    │
│                 │     Domain Model         │                  │
│  ┌──────────────▼─────────────────────────▼────────────┐    │
│  │  VideoSource │ ROIConfig │ AnalysisSession │ Result  │    │
│  └─────────────────────────────────────────────────────┘    │
└───────────────────────┬─────────────────────────────────────┘
                        │ Output Ports
┌───────────────────────▼─────────────────────────────────────┐
│                   DRIVEN ADAPTERS (Output)                   │
│  VideoReader(sv) │ Detector(YOLO) │ Tracker(sv.ByteTrack)   │
│  Zones(sv.LineZone/PolygonZone) │ Storage(CSV/JSON)          │
└─────────────────────────────────────────────────────────────┘
```

---

## Domain Model

### Entities chính

| Entity | Mô tả |
|---|---|
| `VideoSource` | Nguồn video (path, loại: file/stream, metadata) |
| `ROIConfig` | Cấu hình vùng phân tích: danh sách ROI polygon, counting lines, frame_ref |
| `AnalysisSession` | Phiên phân tích: gắn với VideoSource + ROIConfig, có trạng thái |
| `AnalysisResult` | Kết quả một frame/interval: count by type, occupancy, avg_speed |
| `VehicleTrack` | Track của một phương tiện qua các frame (id, type, bbox, positions) |

### Value Objects

```python
@dataclass(frozen=True)
class ROIPolygon:
    name: str
    points: list[tuple[int, int]]  # pixel coordinates

@dataclass(frozen=True)
class CountingLine:
    name: str
    start: tuple[int, int]
    end: tuple[int, int]
    direction: str  # "in" | "out" | "both"

@dataclass(frozen=True)
class VehicleType:
    name: str          # "motorcycle", "car", "truck", "bus"
    pce: float         # Passenger Car Equivalent

@dataclass(frozen=True)
class AnalysisInterval:
    timestamp: datetime
    duration_seconds: float
    vehicle_counts: dict[str, int]   # VehicleType.name -> count
    occupancy_ratio: float           # [0.0, 1.0]
    avg_speed_kmh: float
```

---

## Cấu Trúc Thư Mục

```
traffic-analysis/
├── src/
│   ├── domain/                          # Pure domain logic, không phụ thuộc
│   │   ├── entities/
│   │   │   ├── video_source.py
│   │   │   ├── roi_config.py
│   │   │   ├── analysis_session.py
│   │   │   └── analysis_result.py
│   │   ├── value_objects/
│   │   │   ├── roi_polygon.py
│   │   │   ├── counting_line.py
│   │   │   ├── vehicle_type.py
│   │   │   └── analysis_interval.py
│   │   └── exceptions.py
│   │
│   ├── application/                     # Use cases & ports
│   │   ├── ports/
│   │   │   ├── input/                   # Interfaces cho Driving Adapters
│   │   │   │   ├── roi_config_port.py
│   │   │   │   ├── analysis_port.py
│   │   │   │   └── data_management_port.py
│   │   │   └── output/                  # Interfaces cho Driven Adapters
│   │   │       ├── video_reader_port.py
│   │   │       ├── detector_port.py
│   │   │       ├── tracker_port.py
│   │   │       └── repository_port.py
│   │   └── services/
│   │       ├── roi_config_service.py
│   │       ├── analysis_service.py
│   │       └── data_management_service.py
│   │
│   ├── adapters/
│   │   ├── input/                       # Driving Adapters
│   │   │   ├── cli/
│   │   │   │   └── main_cli.py
│   │   │   └── gui/                     # Optional: Desktop GUI
│   │   │       └── roi_editor_gui.py
│   │   └── output/                      # Driven Adapters
│   │       ├── video/
│   │       │   ├── opencv_video_reader.py
│   │       │   └── frame_annotator.py
│   │       ├── detection/
│   │       │   ├── yolo_detector.py
│   │       │   └── bytetrack_tracker.py
│   │       └── storage/
│   │           ├── json_repository.py
│   │           └── csv_repository.py
│   │
│   └── bootstrap/
│       └── container.py                 # Dependency injection / wiring
│
├── data/
│   ├── sources/                         # Metadata các nguồn video (JSON)
│   ├── configs/                         # ROI configs theo từng nguồn (JSON)
│   └── results/                         # Kết quả phân tích (CSV + JSON)
│
├── models/                              # Pre-trained YOLO weights
├── tests/
│   ├── unit/
│   └── integration/
├── requirements.txt
└── README.md
```

---

## Chi Tiết Các Luồng Nghiệp Vụ

### Luồng 1: Cấu Hình ROI

**Use case flow:**
1. Người dùng cung cấp đường dẫn video/stream
2. `ROIConfigService.extract_reference_frame(source_id)` → lấy frame đầu tiên (hoặc frame do người dùng chọn)
3. Người dùng vẽ ROI polygon + counting lines lên ảnh (GUI editor hoặc công cụ đơn giản)
4. `ROIConfigService.save_config(source_id, roi_config)` → lưu vào `data/configs/<source_id>.json`

**Port/Adapter:**
- Output Port: `VideoReaderPort.get_frame(source, frame_index)` → `np.ndarray`
- Driven Adapter: `OpenCVVideoReader`
- Storage: `ROIConfigRepository.save(config)` → JSON file

**ROI Config JSON schema:**
```json
{
  "source_id": "cam_001",
  "reference_frame_index": 0,
  "roi_polygons": [
    {"name": "lane_1", "points": [[100,200],[400,200],[400,500],[100,500]]}
  ],
  "counting_lines": [
    {"name": "line_in", "start": [100,300], "end": [400,300], "direction": "in"}
  ],
  "pixels_per_meter": 12.5,
  "created_at": "2026-04-29T09:00:00"
}
```

---

### Luồng 1b: Trích Xuất Frame Thử Nghiệm

> **Mục đích:** Trước khi chạy toàn bộ pipeline phân tích batch, người dùng có thể chọn một thời điểm bất kỳ trong video, trích xuất frame tại đó và chạy thử detection ngay lập tức để xác nhận model + ROI hoạt động đúng.

**Use case flow:**
1. Người dùng đã chọn VideoSource trong Source Manager
2. Người dùng kéo **time-slice slider** (hoặc nhập giá trị thời gian `mm:ss` / số frame) để chọn vị trí muốn cắt
3. `FrameExtractionService.extract_frame(source_id, position)` → trả `np.ndarray` của frame tại vị trí đó
   - `position` hỗ trợ: **frame index** (int) hoặc **timestamp (giây)** (float)
   - Internally: `frame_index = int(timestamp_sec * fps)` nếu truyền vào timestamp
4. (Tùy chọn) Người dùng nhấn **"Run Test Detection"**:
   - Gọi `YOLODetector.detect(frame)` → `sv.Detections`
   - Annotate frame với bbox + label loại xe
   - Hiển thị ảnh kết quả ngay trong GUI (không lưu vào storage)
5. (Tùy chọn) Người dùng nhấn **"Save Frame"** → lưu ảnh PNG ra thư mục `data/frames/<source_id>_<frame_index>.png`

**Port/Adapter:**

| Thành phần | Chi tiết |
|---|---|
| Output Port | `VideoReaderPort.get_frame(source_id, frame_index: int) → np.ndarray` |
| Driven Adapter | `SVVideoReader` (dùng `cv2.VideoCapture.set(cv2.CAP_PROP_POS_FRAMES, idx)`) |
| Annotation | `SVFrameAnnotator.annotate(frame, detections) → np.ndarray` |
| Service | `FrameExtractionService` (mới, trong `src/application/services/`) |

**Input Port method (thêm vào `ROIConfigPort` hoặc port riêng):**
```python
class FrameExtractionPort(Protocol):
    def extract_frame(self, source_id: str, frame_index: int) -> np.ndarray: ...
    def extract_frame_at(self, source_id: str, timestamp_sec: float) -> np.ndarray: ...
    def save_frame(self, frame: np.ndarray, source_id: str, frame_index: int) -> Path: ...
```

**`VideoReaderPort` bổ sung method:**
```python
class VideoReaderPort(Protocol):
    # ... các method hiện có ...
    def get_frame(self, source_path: str, frame_index: int) -> np.ndarray: ...
    # Efficient seek: dùng cv2.CAP_PROP_POS_FRAMES thay vì đọc tuần tự
```

**Cập nhật cấu trúc thư mục:**
```
src/application/
├── ports/
│   ├── input/
│   │   ├── frame_extraction_port.py   # [NEW]
│   │   └── ...
│   └── output/
│       └── video_reader_port.py       # Bổ sung get_frame()
└── services/
    ├── frame_extraction_service.py    # [NEW]
    └── ...

data/
└── frames/                            # [NEW] — ảnh PNG đã export
    └── <source_id>_<frame_index>.png
```

**Lưu ý kỹ thuật:**
- Dùng `cv2.VideoCapture.set(cv2.CAP_PROP_POS_FRAMES, idx)` để seek nhanh đến đúng frame, tránh đọc toàn bộ video
- Frame trả về ở định dạng BGR (OpenCV); khi hiển thị trên PyQt6 cần convert sang RGB: `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)`
- Test detection trên frame đơn là stateless — không cần tracker, chỉ cần YOLO + annotator

---

### Luồng 2: Thực Hiện Phân Tích

**Pipeline xử lý mỗi frame (dùng `supervision`):**
```
Frame → YOLO.predict() → sv.Detections (filter vehicle classes)
                              │
                        sv.ByteTrack.update_with_detections()
                              │
              ┌───────────────┼─────────────────┐
       sv.LineZone       sv.PolygonZone      Speed calc
       .trigger()        .trigger()          (track centroid
       → in/out count    → detections_in      displacement)
              │               │                    │
              └───────────────┴────────────────────┘
                         AnalysisInterval
                   (aggregate per 30s interval)
```

**Supervision API sử dụng:**

| Nhu cầu | supervision API |
|---|---|
| Tracker | `sv.ByteTrack` — `tracker.update_with_detections(detections)` |
| Đếm xe qua line | `sv.LineZone` — `line_zone.trigger(detections)` → `in_count`, `out_count` |
| Xe trong vùng ROI | `sv.PolygonZone` — `zone.trigger(detections)` → boolean mask |
| Vẽ bbox + label | `sv.BoundingBoxAnnotator`, `sv.LabelAnnotator` |
| Vẽ track path | `sv.TraceAnnotator` |
| Vẽ counting line | `sv.LineZoneAnnotator` |
| Vẽ ROI zone | `sv.PolygonZoneAnnotator` |
| Đọc video frame | `sv.get_video_frames_generator(source_path)` |
| Metadata video | `sv.VideoInfo.from_video_path(path)` |

**Metrics:**

| Metric | Cách tính với supervision |
|---|---|
| **Vehicle Count** | `sv.LineZone.in_count` + `out_count`, group by VehicleType từ YOLO class_id |
| **Occupancy** | `Σ(bbox_area của detections trong PolygonZone) / zone_area`, avg per interval |
| **Avg Speed** | centroid displacement qua `tracker_id` → `Δpixel / Δframes × fps / pixels_per_meter × 3.6` |

**Output per interval (e.g. 30s):**
```csv
timestamp,session_id,source_id,interval_duration,motorcycle,car,truck,bus,occupancy,avg_speed_kmh
2026-04-29 09:00:00,sess_001,cam_001,30,45,12,2,1,0.35,28.5
```

---

### Luồng 3: Quản Lý Dữ Liệu

**Chức năng:**
- CRUD VideoSource (thêm/sửa/xóa nguồn video)
- Xem danh sách AnalysisSession theo source
- Truy vấn AnalysisResult theo source, khoảng thời gian, loại xe
- Export kết quả ra CSV

**Storage layout:**
```
data/
├── sources/
│   └── sources.json                    # Registry các VideoSource
├── configs/
│   └── <source_id>.json               # ROI config
└── results/
    └── <source_id>/
        ├── sessions.json              # Danh sách AnalysisSession
        └── <session_id>.csv           # Kết quả chi tiết
```

---

## Tech Stack

| Thành phần | Thư viện | Vai trò |
|---|---|---|
| Object Detection | `ultralytics` (YOLOv8n) | Nhận diện phương tiện, trả `sv.Detections` |
| CV Toolkit | `supervision` (roboflow) | Tracker, zones, annotators, video utils |
| Object Tracking | `sv.ByteTrack` | Track ID nhất quán qua frames |
| Counting Line | `sv.LineZone` | Đếm xe vượt line in/out |
| ROI Zone | `sv.PolygonZone` | Lọc & tính occupancy trong vùng ROI |
| Annotation | `sv.BoundingBoxAnnotator`, `sv.TraceAnnotator`, `sv.LineZoneAnnotator`, `sv.PolygonZoneAnnotator` | Vẽ kết quả lên frame |
| Video I/O | `sv.get_video_frames_generator`, `sv.VideoInfo` | Đọc frame, metadata video |
| Desktop GUI | `PyQt6` | 4 màn hình giao diện |
| Storage | `json`, `csv` (stdlib) | Lưu config và kết quả |
| Data Processing | `numpy`, `pandas` | Tính toán metrics |
| Testing | `pytest`, `pytest-mock` | Unit + integration tests |
| Python version | `3.10+` | |

**`requirements.txt`:**
```
ultralytics>=8.0
supervision>=0.25
numpy>=1.24
pandas>=2.0
PyQt6>=6.6
opencv-python>=4.9
pytest>=8.0
pytest-mock>=3.12
```

---

## Kế Hoạch Thực Thi Theo Agent

> [!IMPORTANT]
> Mỗi Agent Phase là một đơn vị công việc độc lập, có đầu vào/đầu ra rõ ràng và kiểm tra hoàn thành trước khi chuyển sang phase tiếp theo. Các phase thực hiện **tuần tự** để tránh đứt đoạn context.

---

### 🔵 Agent Phase 1 — Project Scaffold & Domain Model
**Mục tiêu:** Tạo bộ khung dự án và toàn bộ domain model thuần Python (không phụ thuộc thư viện ngoài)

**Đầu vào:** Thư mục `c:\Archives\Pesonal Projects\traffic-analysis\` (rỗng)

**Việc cần làm:**
- [ ] Tạo cấu trúc thư mục đầy đủ theo layout đã định
- [ ] Tạo `pyproject.toml` / `requirements.txt` với toàn bộ dependencies
- [ ] Implement tất cả **Domain Entities**: `VideoSource`, `ROIConfig`, `AnalysisSession`, `AnalysisResult`, `VehicleTrack`
- [ ] Implement tất cả **Value Objects**: `ROIPolygon`, `CountingLine`, `VehicleType`, `AnalysisInterval`
- [ ] Implement tất cả **Output Ports** (abstract interfaces): `VideoReaderPort`, `DetectorPort`, `TrackerPort`, `RepositoryPort`
- [ ] Implement tất cả **Input Ports** (abstract interfaces): `ROIConfigPort`, `AnalysisPort`, `DataManagementPort`
- [ ] Tạo `domain/exceptions.py`
- [ ] Viết unit tests cho domain logic (pytest)

**Đầu ra / Điều kiện hoàn thành:**
- `pytest tests/unit/` pass 100%
- Không có import nào từ `cv2`, `ultralytics`, `PyQt6` trong `src/domain/` và `src/application/ports/`

---

### 🔵 Agent Phase 2 — Storage Adapters (JSON + CSV)
**Mục tiêu:** Implement tất cả driven adapters liên quan đến lưu trữ dữ liệu

**Đầu vào:** Output của Phase 1 (project scaffold + ports đã định nghĩa)

**Việc cần làm:**
- [ ] `JSONRepository`: lưu/đọc `VideoSource`, `ROIConfig`, `AnalysisSession`
- [ ] `CSVRepository`: append/query `AnalysisInterval` (kết quả theo interval)
- [ ] `DataManagementService`: CRUD VideoSource, list sessions, query results theo time range
- [ ] Implement `DataManagementPort` use case
- [ ] Unit + integration tests cho storage layer

**Storage schema cần implement:**
```
data/
├── sources/sources.json          # [{id, name, path, fps, created_at}]
├── configs/<source_id>.json      # ROIConfig đầy đủ
└── results/<source_id>/
    ├── sessions.json              # [{session_id, started_at, status}]
    └── <session_id>.csv          # interval results
```

**Đầu ra / Điều kiện hoàn thành:**
- Có thể add/list/delete VideoSource qua DataManagementService
- Save và load lại ROIConfig không mất dữ liệu
- Query AnalysisInterval theo time range trả đúng kết quả
- `pytest tests/unit/ tests/integration/storage/` pass

---

### 🔵 Agent Phase 3 — Video & Detection Adapters (ultralytics + supervision)
**Mục tiêu:** Implement các driven adapters xử lý video và nhận diện phương tiện, tận dụng tối đa `supervision`; đồng thời implement luồng trích xuất frame thử nghiệm (Luồng 1b)

**Đầu vào:** Output Phase 1 + 2

**Việc cần làm:**
- [ ] `SVVideoReader` adapter: wrap `sv.VideoInfo.from_video_path()` + `sv.get_video_frames_generator()`, implement `VideoReaderPort`
  - Bổ sung `get_frame(source_path, frame_index)` dùng `cv2.VideoCapture` + `CAP_PROP_POS_FRAMES` seek
- [ ] `YOLODetector` adapter: wrap `ultralytics.YOLO("yolov8n.pt")`, gọi `model(frame)`, convert sang `sv.Detections`, filter `class_id in VEHICLE_CLASSES`, implement `DetectorPort`
- [ ] `SVByteTracker` adapter: wrap `sv.ByteTrack`, gọi `tracker.update_with_detections(detections)`, trả `sv.Detections` có `tracker_id`, implement `TrackerPort`
- [ ] `SVFrameAnnotator`: compose các supervision annotators (`BoundingBoxAnnotator`, `LabelAnnotator`, `TraceAnnotator`), vẽ frame output
- [ ] **[NEW — Luồng 1b]** `FrameExtractionService`: implement `FrameExtractionPort`
  - `extract_frame(source_id, frame_index)` → seek + read 1 frame
  - `extract_frame_at(source_id, timestamp_sec)` → convert sang frame_index rồi seek
  - `save_frame(frame, source_id, frame_index)` → lưu PNG vào `data/frames/`
- [ ] **[NEW — Luồng 1b]** Unit test `FrameExtractionService` với video mẫu
- [ ] Integration test: chạy YOLO + sv.ByteTrack trên video mẫu, verify `tracker_id` nhất quán

**YOLO → VehicleType mapping (COCO class_id):**
```python
VEHICLE_CLASSES = {2, 3, 5, 7}  # car, motorcycle, bus, truck

COCO_TO_VEHICLE_TYPE: dict[int, VehicleType] = {
    2: VehicleType("car",        pce=1.0),
    3: VehicleType("motorcycle", pce=0.5),
    5: VehicleType("bus",        pce=3.0),
    7: VehicleType("truck",      pce=2.5),
}
```

**Pattern sử dụng supervision:**
```python
import supervision as sv
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
tracker = sv.ByteTrack()

for frame in sv.get_video_frames_generator(source_path):
    results = model(frame, verbose=False)[0]
    detections = sv.Detections.from_ultralytics(results)
    detections = detections[np.isin(detections.class_id, list(VEHICLE_CLASSES))]
    detections = tracker.update_with_detections(detections)
    # detections.tracker_id available here
```

**Đầu ra / Điều kiện hoàn thành:**
- `SVVideoReader.get_video_info()` trả đúng fps, total_frames, resolution
- `YOLODetector.detect(frame)` trả `sv.Detections` chỉ chứa vehicle classes
- `SVByteTracker.update(detections)` trả `sv.Detections` với `tracker_id` nhất quán qua frames

---

### 🔵 Agent Phase 4 — Analysis Engine (supervision zones + metrics)
**Mục tiêu:** Implement `AnalysisService` — engine tính toán 3 metrics chính, dùng `sv.LineZone` và `sv.PolygonZone`

**Đầu vào:** Output Phase 1, 2, 3

**Việc cần làm:**
- [ ] **Counting Line Crossing** — dùng `sv.LineZone`:
  ```python
  line_zone = sv.LineZone(start=sv.Point(*cfg.start), end=sv.Point(*cfg.end))
  crossed_in, crossed_out = line_zone.trigger(detections)
  # group counts by class_id → VehicleType
  ```
- [ ] **Occupancy Calculation** — dùng `sv.PolygonZone`:
  ```python
  zone = sv.PolygonZone(polygon=np.array(cfg.points))
  in_zone_mask = zone.trigger(detections)          # boolean mask
  bbox_areas   = (detections.xyxy[:,2]-detections.xyxy[:,0]) * \
                 (detections.xyxy[:,3]-detections.xyxy[:,1])
  occupancy    = bbox_areas[in_zone_mask].sum() / zone.area
  ```
- [ ] **Speed Estimation** — dùng `tracker_id` từ `sv.ByteTrack`:
  ```python
  # Lưu centroid history per tracker_id
  speed_kmh = delta_pixels / delta_frames * fps / pixels_per_meter * 3.6
  # Lọc outlier: chỉ tính track đã xuất hiện >= min_frames
  ```
- [ ] `AnalysisService.run_session(session_id)`: orchestrate pipeline, aggregate metrics theo interval (mặc định 30s), lưu qua `RepositoryPort`
- [ ] Unit test từng metric với `sv.Detections` mock
- [ ] Integration test: chạy full session trên video mẫu, verify CSV output

**Đầu ra / Điều kiện hoàn thành:**
- CSV output đúng schema, số liệu hợp lý với video test
- Unit test covering: `LineZone` count in/out by VehicleType, `PolygonZone` occupancy, speed formula

---

### 🔵 Agent Phase 5 — Desktop GUI (PyQt6)
**Mục tiêu:** Xây dựng giao diện Desktop GUI đầy đủ 3 luồng nghiệp vụ

**Đầu vào:** Output Phase 1–4 (toàn bộ backend hoạt động)

**Các màn hình cần implement:**

#### Screen 1: Source Manager
- Danh sách VideoSource (table)
- Thêm/xóa source (chọn file video)
- Nút → mở ROI Config cho source đã chọn
- Nút → chạy Analysis Session
- Nút → xem kết quả

#### Screen 2: ROI Config Editor + Frame Test
- Hiển thị reference frame (frame đầu video mặc định)
- **Time-slice selector** — hai cách nhập (sync với nhau):
  - Slider kéo theo frame index (0 → total_frames - 1)
  - Input `mm:ss` hoặc số giây để nhảy đến timestamp chính xác
- Nút **"Go to Frame"** → gọi `FrameExtractionService.extract_frame()`, cập nhật ảnh hiển thị ngay lập tức
- **Tool vẽ ROI Polygon**: click để thêm điểm, đóng polygon
- **Tool vẽ Counting Line**: click 2 điểm, chọn hướng (in/out/both)
- Input `pixels_per_meter`: nhập giá trị hiệu chuẩn
- Nút **"Run Test Detection"** (Luồng 1b):
  - Chạy `YOLODetector.detect(current_frame)` trên frame đang hiển thị
  - Overlay bbox + label lên ảnh (không lưu vào storage)
  - Hiển thị summary nhỏ: tổng số xe phát hiện theo từng loại
- Nút **"Save Frame as PNG"** → `FrameExtractionService.save_frame()` → lưu ra `data/frames/`
- Nút Save Config / Load Config

#### Screen 3: Analysis Dashboard
- Progress bar khi đang phân tích
- Live preview frame (tùy chọn — skip nếu ảnh hưởng performance)
- Kết quả dạng bảng: vehicle count by type, occupancy %, avg speed
- Chart đơn giản: timeline count/occupancy

#### Screen 4: Results Viewer
- Filter theo source, khoảng thời gian
- Bảng kết quả interval
- Export CSV button

**Đầu ra / Điều kiện hoàn thành:**
- Toàn bộ 3 luồng nghiệp vụ hoàn chỉnh qua GUI
- Không crash khi xử lý video > 5 phút

---

### 🔵 Agent Phase 6 — Integration, Polish & Documentation
**Mục tiêu:** Kiểm thử end-to-end, hoàn thiện UX và viết README

**Đầu vào:** Output Phase 1–5

**Việc cần làm:**
- [ ] End-to-end test: thêm source → config ROI → chạy analysis → xem kết quả
- [ ] Xử lý edge cases: video rỗng, không có xe trong frame, ROI nằm ngoài frame
- [ ] Error handling thân thiện trong GUI (dialog thay vì crash)
- [ ] `README.md`: hướng dẫn cài đặt, cách dùng từng luồng, ví dụ
- [ ] Kiểm tra performance: video 10 phút, 1080p → thời gian xử lý chấp nhận được
- [ ] Packaging: script `run.bat` để chạy trên Windows

**Đầu ra / Điều kiện hoàn thành:**
- Demo video ngắn toàn bộ workflow
- `README.md` đầy đủ
- Không có exception unhandled trong GUI

---

## Verification Plan

### Automated Tests
```bash
pytest tests/unit/                    # Domain logic tests
pytest tests/integration/             # Adapter integration tests
```

### Manual Verification
1. Chạy ROI config tool trên video mẫu → verify frame capture + JSON output đúng schema
2. Chạy analysis trên đoạn video test có xe rõ ràng → kiểm tra count, occupancy, speed hợp lý
3. Query kết quả theo khoảng thời gian → verify CSV output đúng format

---

## Điểm Mở Rộng Trong Tương Lai (nhờ Hexagonal Arch)

| Nâng cấp | Thay đổi cần thiết |
|---|---|
| Thêm RTSP stream | Chỉ thêm `RTSPVideoReader` adapter |
| Đổi sang PostgreSQL | Chỉ thêm `PostgresRepository` adapter |
| Thêm Web API | Thêm `FastAPI` driving adapter |
| Đổi model detection | Chỉ thêm `CustomModelDetector` adapter |
| Thêm heat map | Thêm use case, không đụng domain cũ |
