# Risks, Rollback & Decision Log

## Rủi ro & mitigation

| # | Rủi ro | Tác động | Mitigation |
|---|---|---|---|
| R1 | Đổi format `sources.json` (absolute → relative path) làm hỏng dữ liệu cũ | Cao — mất tham chiếu video | Migration script idempotent ở Phase 1; backup `data/` trước khi run script; tài liệu hoá rollback (giữ bản sao `sources.json.bak`) |
| R2 | YOLO Ultralytics tự ghi cache vào HOME khi không set `YOLO_CONFIG_DIR` | Trung — pollute home volume / lỗi permission trong container | Set `YOLO_CONFIG_DIR=/app/models/.ultralytics` trong Dockerfile; verify ở smoke test |
| R3 | `opencv-python` (đang dùng) yêu cầu libGL → image phình to & dễ lỗi | Trung — image lớn / runtime error | Dùng `opencv-python-headless` trong `requirements-prod.txt`; tách `requirements-dev.txt` cho local PyQt6 dev |
| R4 | Upload video lớn (> 1 GB) qua HTTP timeout / OOM | Cao — UX kém | MVP: giới hạn 500 MB qua reverse proxy; CLI ingest cho video lớn (file 05); nâng cấp tus protocol nếu cần |
| R5 | WebSocket bị reverse proxy / firewall chặn | Trung — không thấy progress | Tài liệu hoá nginx WS config trong file 06; fallback polling `GET /api/sessions/{id}` mỗi 2s nếu WS thất bại |
| R6 | Đồng thời nhiều phiên phân tích → GPU OOM | Cao — crash | `TRAFFIC_MAX_JOBS=1` mặc định; queue 409 nếu vượt; tài liệu hoá scaling sau (nhiều container + load balancer) |
| R7 | Frontend build artifact phình image | Thấp | Multi-stage build, chỉ copy `dist/` (không node_modules) |
| R8 | API breaking khi đổi schema sau Phase 4 | Cao — frontend break | Khoá API contract sau Phase 2; mọi thay đổi versioned (`/api/v2/...`); generate types từ OpenAPI |
| R9 | PyQt6 import errors khi build production image (vẫn còn import trong code path) | Trung — image build fail | Trước khi build, audit: `grep -r "from PyQt6" src/` chỉ còn trong `src/adapters/input/gui/`; web app không import gui |
| R10 | Cancel session không kịp (loop chỉ check flag mỗi N frame) | Thấp — chậm cancel vài giây | Tài liệu hoá: cancel có thể mất tới `frame_skip × 100` frames; chấp nhận trade-off |
| R11 | User upload file không phải video → server crash khi đọc metadata | Trung | Validate magic bytes / extension + try/except quanh `SVVideoReader.get_video_info()`; trả 400 với detail rõ |
| R12 | Path traversal qua `POST /api/sources/scan` | Cao (security) | Resolve và check `is_relative_to(data_dir)` strict; reject bất kỳ `..` |
| R13 | Hot reload `inference.yaml` qua UI bị race với phiên đang chạy | Trung | `Container.analysis_service()` snapshot config khi khởi tạo; reload chỉ reset `_detector` cache; phiên đang chạy giữ instance cũ. **Phải có test chứng minh invariant này** ở Phase 1. |
| R14 | Mount volume `models/` RO nhưng Ultralytics auto-download cần ghi | Trung | Đặt `YOLO_CONFIG_DIR=/app/models/.ultralytics` và mount `models/` RW (xem file 06), hoặc preload weights trước khi up |
| R15 | UI lưu `inference.yaml` làm mất comment / xáo format | Thấp — UX | Dùng `ruamel.yaml` (preserve mode); fallback `pyyaml` nếu thư viện gặp issue → chấp nhận mất comment, có cảnh báo trong README |
| R16 | Atomic write YAML fail giữa chừng → file rỗng / corrupt | Cao — mất config | Pattern: ghi `inference.yaml.tmp` → `os.replace()` → backup `inference.yaml.bak` trước khi ghi. Test crash giữa chừng. |
| R17 | UI lưu config invalid bypass validation client-side (curl thẳng) → backend save xong mới phát hiện weights không load được | Trung | Validate trên backend trước khi ghi YAML; với weights, optional dry-run YOLO load → reject 503 nếu fail (không ghi). |
| R18 | Mount file đơn lẻ `inference.yaml:ro` không cho phép atomic rename trong container | Trung | Mount cả thư mục `config/` thay vì file đơn lẻ (đã sửa trong file 06) |
| R19 | User dùng UI sửa config trong khi CLI cũ đang chạy → race condition | Thấp | CLI load config 1 lần khi khởi động; không có shared state. Reload chỉ ảnh hưởng web container. |
| R20 | Download bundle ZIP load full vào RAM → OOM container | Cao — crash | Dùng `zipstream-ng` (generator-based, không buffer); StreamingResponse stream chunk thẳng cho client. Test với bundle 1 GB và mem limit 512 MB. |
| R21 | Download annotated video qua reverse proxy bị buffer (nginx mặc định buffer response) → tăng latency + tốn disk tmp | Trung | Set `proxy_buffering off` cho path `/api/sessions/.+/download/...` (tài liệu hoá trong file 06) |
| R22 | Browser fetch + Blob() cho file > 50MB → tab OOM | Trung — UX | Dùng anchor `<a download>` cho tất cả link tải; KHÔNG fetch+blob (đã ghi rõ trong file 04) |
| R23 | Race: client request `/download/video` khi render chưa xong → trả 404 nhầm "không có" | Thấp — UX nhầm lẫn | Phân biệt: 404 = session không bật `render_video`; 425 Too Early = đang render hoặc session chưa completed. UI hiển thị message khác nhau. |
| R24 | Path traversal qua `session_id` trong download endpoint | Cao (security) | Validate `session_id` regex `^sess_[a-z0-9]+$`; resolve file path qua repository, check `is_relative_to(data_dir)` strict. |
| R25 | User huỷ download giữa chừng, FastAPI giữ generator zipstream → leak file handle | Thấp | `StreamingResponse` của FastAPI tự cleanup khi client disconnect; verify bằng test (`asyncio.CancelledError` propagate đúng). |
| R26 | Annotated video render block thread pool → các session khác phải đợi | Trung | Render phải chạy cùng worker với analysis (tuần tự, dùng chung `TRAFFIC_MAX_JOBS`). Tài liệu hoá: bật `render_video` tăng tổng wall-clock của job. |

## Rollback plan

### Rollback từng phase

| Phase | Rollback action |
|---|---|
| 1 (path refactor) | `git revert` commits; restore `sources.json.bak` nếu đã chạy migration |
| 2 (FastAPI) | `git revert`; CLI/GUI vẫn chạy không phụ thuộc web |
| 3 (jobs/WS) | Disable WS endpoint, frontend fallback polling |
| 4 (frontend) | Build artifact vô hại — xoá `frontend/dist`, vẫn còn API |
| 5 (Docker) | `docker compose down`; chạy native qua `python -m src.adapters.input.web.app` |
| 6 (deprecate PyQt6) | PyQt6 vẫn ở `requirements-dev.txt`, không xoá khỏi codebase ngay |

### Rollback toàn diện (về desktop-only)

Nếu phải bỏ web migration:
1. Tag mốc: `git tag pre-web-migration` trước Phase 1.
2. Rollback: `git checkout pre-web-migration`.
3. `data/` không thay đổi schema (nếu chưa chạy Phase 1 migration) — chạy thẳng PyQt6 GUI lại.
4. Nếu đã chạy migration script và muốn về absolute path: viết script ngược, đọc `data_dir` + relative → absolute.

> **Khuyến nghị:** giữ branch `web-migration` riêng cho đến hết Phase 5; chỉ merge `main` sau khi Phase 5 verify pass.

## Decision log

> Ghi mọi quyết định kiến trúc/công nghệ phát sinh trong quá trình triển khai. Format: ngày, quyết định, lý do, alternatives đã loại.

### 2026-05-08 — FastAPI thay vì Flask
- **Lý do:** OpenAPI auto-generate, native WebSocket, async, Pydantic validation tích hợp. Codebase đã dùng dataclass nên Pydantic dễ tiếp cận.
- **Alternatives loại:** Flask (cần extension cho WS + schema); Django (over-kill).

### 2026-05-08 — React thay vì Vue/Svelte
- **Lý do:** ecosystem canvas/upload tốt nhất; team có thể tìm dev React dễ hơn; có TanStack Query mature.
- **Alternatives loại:** Vue 3 (nhỏ hơn, ổn nhưng ít component canvas sẵn); Svelte (sexy nhưng nhỏ team).

### 2026-05-08 — Single container thay vì microservice
- **Lý do:** state in-memory cho jobs đơn giản; chưa cần scale; deploy/operate dễ.
- **Alternatives loại:** API + worker tách container với Redis broker — cân nhắc khi `TRAFFIC_MAX_JOBS` cần > 1 và cần persist queue qua restart.

### 2026-05-08 — Bỏ phạm vi realtime / streaming
- **Lý do:** workflow đang phục vụ phân tích sau-quay (batch); thêm realtime kéo theo RTSP, frame buffer, latency tuning, GPU contention với job batch — không xứng cost cho use case hiện tại.
- **Alternatives loại:** RTSP adapter + WS frame stream — defer hẳn, chưa có decision date cho phase sau.

### 2026-05-08 — Luồng Download Artifacts là first-class workflow
- **Lý do:** sau khi phân tích xong, user cần lấy về CSV, video annotated, summary. Mở terminal cp file từ container hoặc rsync data/ là rào cản UX. Web phải có panel "Tải kết quả" gọn.
- **Quyết định kèm theo:**
  - Thêm option `render_video: bool` trong POST sessions (default false) — không bắt buộc render mọi lần (tốn 1.5–2× thời gian).
  - Generate `summary.json` bắt buộc khi completed — rẻ, hữu ích cho dashboard.
  - Bundle ZIP stream qua `zipstream-ng` — không buffer RAM.
  - Reuse anchor download (`<a download>`) thay vì fetch+blob để hỗ trợ file lớn.
- **Alternatives loại:**
  - Pre-zip ngay khi completed: tốn disk gấp đôi cho file lớn, user có thể không cần ZIP.
  - Generate signed URL (S3-style): over-engineer khi mọi thứ trên local volume.

### 2026-05-08 — UI cấu hình tham số mô hình thay vì sửa YAML thủ công (first-class workflow)
- **Lý do:** mục tiêu Docker = vận hành không cần shell vào container; YAML không thân thiện non-dev; risk sai cú pháp YAML cao.
- **Alternatives loại:** giữ chỉ-YAML + tool dòng lệnh helper — ít UX value; web UI thêm 1 trang form đáng đầu tư.
- **Hệ quả:**
  - Mount `config/` đổi từ RO → RW.
  - Thêm dependency `ruamel.yaml` để giữ comment.
  - Cần endpoint hot-reload + invariant "phiên đang chạy không bị ảnh hưởng" (R13).
  - Cần `GET /api/config/inference/schema` để UI render form data-driven.

### _yyyy-mm-dd_ — _decision_
- **Lý do:** ...
- **Alternatives loại:** ...

## Known limitations (đã chấp nhận)

- Không hỗ trợ multi-user / auth ở MVP. Triển khai nội bộ behind VPN/reverse-proxy với basic auth.
- **Chỉ phân tích batch trên video đã upload** — không có realtime / RTSP / webcam.
- Cancel session không tức thời (xem R10).
- Phân tích chỉ chạy 1 phiên đồng thời mặc định.
- ~~Sửa `inference.yaml` cần restart container.~~ **Đã giải quyết:** UI Inference Settings + hot-reload Container.
- Hot-reload config chỉ áp cho phiên **mới**; phiên đang chạy giữ snapshot cũ — đây là tradeoff có chủ ý (tránh corrupt session đang chạy).
- Không có persistence cho job queue qua restart (job đang chạy → marked `failed`).
- Mobile/touch không hỗ trợ ROI editor.
- UI Inference Settings không hỗ trợ multi-version config / preset save — chỉ 1 config global (preset workflow defer Phase sau).

## Open questions cần trả lời trước Phase tương ứng

- **Trước Phase 2:** chunked upload protocol — multipart đơn giản hay tus.io? (mặc định: multipart)
- **Trước Phase 3:** persistence cho job state — in-memory hay SQLite? (mặc định: in-memory + lưu trạng thái cuối qua SessionRepository)
- **Trước Phase 5:** GPU base image — `nvidia/cuda:12.4-runtime` hay `pytorch/pytorch:2.x-cuda`? (so sánh size + ultralytics compat trước khi quyết)
- **Trước Phase 6:** giữ PyQt6 GUI tới phiên bản nào? (đề xuất: 2 minor versions sau khi web stable)
