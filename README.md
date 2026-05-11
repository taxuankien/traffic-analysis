# Traffic Analysis

Hệ thống phân tích giao thông từ video (mp4/avi) — đếm xe theo loại, đo độ chiếm dụng và vận tốc trung bình. Kiến trúc Hexagonal (Ports & Adapters), GUI PyQt6.

## Cài đặt

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows
pip install -r requirements.txt
```

YOLO weights `yolov8n.pt` sẽ được Ultralytics tự tải về lần đầu chạy. Có thể đặt sẵn vào `models/yolov8n.pt`.

## Cấu hình mô hình

Toàn bộ tham số ảnh hưởng đến kết quả dự đoán (confidence, IoU, kích thước ảnh, ngưỡng tracker, PCE…) được tập trung tại [config/inference.yaml](config/inference.yaml). Chương trình tự load file này khi khởi động (GUI và CLI). CLI có thêm cờ `--config <path>` để dùng file khác.

Tài liệu chi tiết về từng tham số + preset cho **video độ phân giải thấp** và **mật độ xe máy cao (giao thông VN)**: xem [docs/INFERENCE_TUNING.md](docs/INFERENCE_TUNING.md).

## Chạy GUI

```bash
run.bat
# hoặc
python -m src.adapters.input.gui.app
```

GUI có 4 màn hình điều hướng bằng nút **Quay lại**:

1. **Source Manager** — thêm/xoá nguồn video, chọn thao tác (cấu hình ROI / phân tích / xem kết quả).
2. **ROI Config Editor + Frame Test** — kéo slider hoặc nhập `mm:ss` / số giây + bấm "Go to Frame" để nhảy đến vị trí bất kỳ. Vẽ polygon ROI (click thêm điểm, double-click để đóng), vẽ counting line (2 click). Nhập `pixels_per_meter` để bật tính vận tốc. Hai nút thử nghiệm:
   - **Run Test Detection** — chạy YOLO trên frame hiện tại, overlay bbox + label, hiển thị summary số xe theo loại (không lưu vào storage).
   - **Save Frame as PNG** — lưu frame (gốc hoặc đã annotate) ra `data/frames/`.
3. **Analysis Dashboard** — chọn interval (giây), bấm Bắt đầu. Worker thread chạy YOLO + ByteTrack + zones; progress bar cập nhật, bảng hiển thị kết quả khi hoàn tất.
4. **Results Viewer** — lọc theo session/khoảng thời gian, xuất CSV.

## Chạy bằng CLI

```bash
# Thêm nguồn
python -m src.adapters.input.cli.main_cli add-source "Cam 1" data/vehicles.mp4

# Đặt ROI: 1 polygon + 1 line, hệ số hiệu chuẩn 12.5 px/m
python -m src.adapters.input.cli.main_cli set-roi <source_id> \
  --polygon "0,300;1920,300;1920,800;0,800" \
  --line "0,500;1920,500" \
  --pixels-per-meter 12.5

# Phân tích, xuất video annotated tuỳ chọn
python -m src.adapters.input.cli.main_cli run <source_id> --interval 30 --output result.mp4

# Trích xuất frame riêng lẻ (Luồng 1b) — chỉ định frame index hoặc timestamp
python -m src.adapters.input.cli.main_cli extract-frame <source_id> --time 1.5
python -m src.adapters.input.cli.main_cli extract-frame <source_id> --frame 38

# One-shot test detection trên 1 frame, lưu PNG đã annotate
python -m src.adapters.input.cli.main_cli test-detect <source_id> --time 1.5 --output result/test.png

# Preview slice [start, end) — annotate từng frame, lưu PNG
python -m src.adapters.input.cli.main_cli preview <source_id> --start 30 --end 50 --out-dir result/preview

# Render full video annotated (bbox, trace, ROI overlay, counter overlay) — tương đương result/result.mp4
python -m src.adapters.input.cli.main_cli render <source_id> --output result/annotated.mp4
```

## Kiến trúc

```
src/
├── domain/           # Entities + value objects (thuần Python)
├── application/
│   ├── ports/        # Interfaces (input + output)
│   └── services/     # Use cases: ROIConfig, Analysis, DataManagement
├── adapters/
│   ├── input/        # CLI, GUI (PyQt6)
│   └── output/       # SVVideoReader, YOLODetector, SVByteTracker, Storage
└── bootstrap/        # Container DI
```

## Storage layout

```
data/
├── sources/sources.json         # Registry các VideoSource
├── configs/<source_id>.json     # ROI config theo source
├── frames/                      # PNG đã trích xuất (Luồng 1b)
│   └── <source_id>_<frame>.png
└── results/<source_id>/
    ├── sessions.json            # Danh sách session
    └── <session_id>.csv         # Kết quả interval (1 dòng / interval)
```

CSV columns: `timestamp, duration_seconds, occupancy_ratio, avg_speed_kmh, bus, car, motorcycle, truck`.

## Test

```bash
.venv\Scripts\python -m pytest tests/unit/         # domain logic
.venv\Scripts\python -m pytest tests/integration/  # adapters + e2e
.venv\Scripts\python -m pytest tests/              # tất cả
```

Tests phụ thuộc YOLO + sample video sẽ tự skip nếu thiếu file.

## Mở rộng

| Nâng cấp | Thay đổi |
|---|---|
| RTSP stream | Thêm `RTSPVideoReader(VideoReaderPort)` |
| PostgreSQL | Thêm `PostgresXxxRepository(...)` |
| Web API | Thêm FastAPI driving adapter, gọi cùng services |
| Đổi model detection | Thêm `CustomDetector(DetectorPort)` |
