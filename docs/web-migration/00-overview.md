# Web Migration & Dockerization — Overview

## Mục tiêu

Chuyển hệ thống `traffic-analysis` hiện tại (PyQt6 desktop GUI + CLI) sang **kiến trúc web-based** (REST/WebSocket API + SPA frontend) và đóng gói thành **Docker image** triển khai được, với `data/` và `models/` được mount qua **volume** thay vì nằm trong image.

Mục tiêu này không thay đổi phần lõi nghiệp vụ (`domain/` + `application/services/`) — kiến trúc Hexagonal sẵn có cho phép thêm một **driving adapter HTTP** mới song song với CLI/GUI hiện tại.

## Phạm vi

| Hạng mục | Trong phạm vi | Ngoài phạm vi |
|---|---|---|
| Backend HTTP API (FastAPI) | ✅ | gRPC, GraphQL |
| Frontend SPA (React + Vite) | ✅ | SSR/Next.js, mobile native |
| Web ROI editor (canvas vẽ polygon/line) | ✅ | Vẽ ROI 3D, nhiều layer |
| Phân tích video đã upload (batch) | ✅ | **Phân tích realtime** (RTSP/webcam stream live) |
| WebSocket cho progress phân tích batch | ✅ | Stream frame live qua WS |
| Upload video qua web (chunked/multipart) | ✅ | Upload từ S3/cloud trực tiếp |
| **Cấu hình tham số mô hình qua UI** (thay cho sửa `config/inference.yaml`) | ✅ | Thay đổi model architecture (chỉ cấu hình tham số inference) |
| **Tải kết quả phân tích về client** (CSV, annotated video, ZIP bundle) | ✅ | Streaming live frame; chia chunk download với resume |
| Dockerfile + docker-compose | ✅ | Kubernetes manifests, Helm chart |
| GPU support trong container | ✅ (tài liệu hoá) | Multi-GPU scheduler |
| Auth/Multi-tenant | ❌ (deploy nội bộ; dự phòng cho phase sau) | |
| PostgreSQL/queue | ❌ (giữ JSON/CSV; chỉ thêm WebSocket) | |
| Giữ PyQt6 GUI hoạt động | ✅ (deprecate dần, không xoá ngay) | |

> **Phạm vi phân tích:** Hệ thống chỉ xử lý **video đã upload** (file .mp4/.avi). Không stream camera live, không kết nối RTSP. Mọi phiên phân tích là batch — bắt đầu khi user bấm nút, chạy đến khi hết video hoặc bị huỷ. WebSocket trong scope chỉ phục vụ progress của job batch.

## Nguyên tắc thiết kế

1. **Domain & application services không đổi.** Web chỉ là driving adapter mới (`src/adapters/input/web/`). Mọi service hiện có (`AnalysisService`, `ROIConfigService`, `DataManagementService`, `FrameExtractionService`, `VisualizationService`) được tái sử dụng nguyên xi.
2. **Stateless API request, stateful job qua background task.** Phân tích là long-running → chạy trong worker (FastAPI `BackgroundTasks` hoặc thread pool); client subscribe progress qua WebSocket.
3. **Không hardcode đường dẫn tuyệt đối.** Toàn bộ path neo theo biến môi trường (`TRAFFIC_DATA_DIR`, `TRAFFIC_MODELS_DIR`, `TRAFFIC_CONFIG_DIR`) thay vì `PROJECT_ROOT`. Quan trọng cho Docker volume mount.
4. **Phân tách mount-points rõ ràng.** `data/` (read-write) và `models/` (read-only thường thấy) là 2 volume riêng. `config/inference.yaml` mount RW (vì UI sẽ ghi vào — xem nguyên tắc 6).
5. **Tương thích ngược trong giai đoạn chuyển tiếp.** CLI và PyQt6 GUI vẫn chạy được trên cùng codebase đến hết Phase 4. Loại bỏ PyQt6 dependency khỏi image production sau Phase 5.
6. **Cấu hình mô hình là first-class workflow.** Người dùng cuối **không cần SSH/exec vào container** để sửa YAML. Một trang UI riêng cho phép xem + sửa toàn bộ tham số trong `inference.yaml` (model, detection, tracking, speed, analysis, queue, vehicle_pce). Backend persist xuống cùng file YAML để CLI/GUI cũ vẫn đọc được, và hot-reload Container DI để áp dụng ngay không cần restart.

## Kết quả mong đợi

- `docker compose up` khởi chạy được toàn bộ (web frontend + API + sample volume).
- Người dùng truy cập `http://localhost:8080`, thực hiện đủ **6 luồng**: thêm nguồn (upload) → cấu hình ROI → **cấu hình tham số mô hình** → phân tích batch → xem kết quả → **tải artifacts (CSV/video annotated/ZIP)**.
- Không cần mở terminal hay sửa file YAML để vận hành hệ thống ở mức cơ bản.
- Image production có size < 4 GB (CPU build) / < 6 GB (CUDA build).
- Không bao giờ lưu video/model bên trong image; restart container không mất dữ liệu.

## Cấu trúc bộ tài liệu này

| File | Nội dung |
|---|---|
| `00-overview.md` | (file này) Mục tiêu, phạm vi, nguyên tắc |
| `01-implementation-plan.md` | Chi tiết 6 phase + deliverables |
| `02-phase-tracker.md` | Bảng theo dõi tiến độ — cập nhật khi triển khai |
| `03-architecture-and-api.md` | Sơ đồ kiến trúc mới + REST/WebSocket spec |
| `04-frontend-ux.md` | Wireframe 4 màn hình web + flow tương tác |
| `05-data-source-workflow.md` | Luồng nghiệp vụ thêm nguồn / cấu hình mới phù hợp web |
| `06-docker-deployment.md` | Dockerfile, compose, volume layout, GPU |
| `07-risks-and-rollback.md` | Rủi ro, plan rollback, decision log |

## Cách dùng tài liệu

- Đọc `00` → `01` → `03`/`04`/`05` để nắm đầy đủ thiết kế trước khi viết code.
- Trong quá trình triển khai, **chỉ cập nhật `02-phase-tracker.md`** mỗi cuối phase (đánh dấu task done, ghi chú deviation).
- Khi có quyết định kiến trúc mới/đổi, ghi vào "Decision log" trong `07-risks-and-rollback.md` — không sửa lùi `01`.
