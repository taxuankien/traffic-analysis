# Web Migration & Dockerization Plan

Bộ tài liệu kế hoạch chuyển hệ thống `traffic-analysis` từ desktop GUI (PyQt6) sang web-based (FastAPI + React) và đóng gói Docker với volume mount cho `data/` và `models/`.

| File | Nội dung |
|---|---|
| [00-overview.md](00-overview.md) | Mục tiêu, phạm vi, nguyên tắc thiết kế |
| [01-implementation-plan.md](01-implementation-plan.md) | 6 phase triển khai chi tiết + DoD |
| [02-phase-tracker.md](02-phase-tracker.md) | Bảng theo dõi tiến độ — cập nhật khi triển khai |
| [03-architecture-and-api.md](03-architecture-and-api.md) | Sơ đồ kiến trúc + REST/WebSocket API spec |
| [04-frontend-ux.md](04-frontend-ux.md) | Wireframe 4 màn hình web + flow tương tác |
| [05-data-source-workflow.md](05-data-source-workflow.md) | Luồng nghiệp vụ thêm nguồn / cấu hình mới |
| [06-docker-deployment.md](06-docker-deployment.md) | Dockerfile, compose, volume, GPU, troubleshooting |
| [07-risks-and-rollback.md](07-risks-and-rollback.md) | Rủi ro, rollback plan, decision log |

## Đọc theo thứ tự nào?

- **Lần đầu:** `00` → `01` → `03` → `04` → `05` → `06` → `07`.
- **Khi triển khai:** mở `01` (xác định phase đang làm) + `02` (tick checklist) + file chuyên sâu tương ứng (`03/04/05/06`).
- **Khi gặp deviation:** ghi vào `02` ("Deviation / Note") và `07` ("Decision log") — không sửa lùi `01`.

## Phạm vi (đã chốt)

- **Chỉ phân tích batch** trên video đã upload. Không có RTSP / webcam / streaming live.
- **Cấu hình mô hình qua UI** — thay thế việc sửa `config/inference.yaml` thủ công. Hot-reload, không cần restart container.

## 6 luồng nghiệp vụ web

1. Thêm nguồn (upload video) — Page Sources
2. Cấu hình ROI per-source — Page ROI Editor
3. **Cấu hình tham số mô hình toàn cục** — Page Inference Settings (mới)
4. Phân tích batch (option render annotated video) — Page Analysis (WS progress)
5. Xem kết quả — Page Results (bảng intervals + summary)
6. **Tải kết quả về client** — Panel "Tải kết quả" trên Page Results: CSV, summary.json, ROI config, annotated.mp4 (nếu có), bundle ZIP. Stream qua FastAPI StreamingResponse / zipstream-ng.

## Phase ngắn gọn

```
Phase 1: Path & Config Refactor + Inference Repo   (1–2 ngày)
Phase 2: Backend HTTP API + Inference endpoints     (5–6 ngày)
Phase 3: Background Job + WS (batch only)           (2–3 ngày)   ┐ song song được sau khi
Phase 4: Frontend SPA (5 trang)                     (6–8 ngày)   ┘ Phase 2 stable
Phase 5: Dockerization                              (2–3 ngày)
Phase 6: Polish & Deprecate                         (2 ngày)
```

Tổng ước lượng: ~3–4 tuần dev time.
