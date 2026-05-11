# Frontend UX — 5 màn hình web

> Mục đích: mô tả wireframe, flow tương tác, và component map cho SPA. Không bao gồm CSS/style chi tiết — để cho dev frontend quyết.
>
> **Phạm vi phân tích:** chỉ batch trên video đã upload. Không có UI cho stream live / RTSP.

## Stack đề xuất

| | Lựa chọn | Lý do |
|---|---|---|
| Framework | React 18 + TypeScript | Phổ biến, ecosystem tốt cho canvas |
| Build | Vite | Dev experience nhanh, proxy `/api` dễ |
| Routing | React Router v6 | Đủ dùng cho 4 trang |
| Data fetching | TanStack Query | Cache + invalidation tự động |
| State (local) | useState/useReducer | Không cần Redux |
| WebSocket | Native `WebSocket` API + custom hook `useSessionProgress` | |
| Styling | TailwindCSS | Nhanh, không cần thiết kế CSS riêng |
| Canvas vẽ ROI | HTML `<canvas>` thuần (không cần Konva/Fabric) | Số shape ít, đơn giản |
| Form | react-hook-form (optional) | Cho ROI numeric inputs |

## Layout chung

```
┌──────────────────────────────────────────────────────────────┐
│  TopBar:  [Logo] Traffic Analysis                            │
│           [Sources] [Inference Settings ⚙]   [Monitor pill]  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│             <Outlet /> — current page                        │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  Footer: backend version • API docs link                     │
└──────────────────────────────────────────────────────────────┘
```

- TopBar có 2 link điều hướng chính: `Sources` (workflow per-video) và `Inference Settings` (config toàn cục).
- `Monitor pill` polling `GET /api/system/monitor` mỗi 5s, hiển thị CPU% / GPU%.

---

## Page 1 — Sources (`/sources`, default)

### Wireframe

```
┌──────────────────────────────────────────────────────────────┐
│  Nguồn video                              [+ Thêm video]      │
├────┬───────────────┬──────────────┬──────────────┬───────────┤
│ ID │ Tên           │ Đường dẫn    │ Tạo lúc      │ Hành động │
├────┼───────────────┼──────────────┼──────────────┼───────────┤
│ s1 │ Cam 1 - QL1   │ uploads/...  │ 2026-05-08   │ ⚙ ▶ 📊 🗑  │
│ s2 │ Cam 2 - Cầu   │ uploads/...  │ 2026-05-07   │ ⚙ ▶ 📊 🗑  │
└────┴───────────────┴──────────────┴──────────────┴───────────┘
```

Action icons: ⚙ Cấu hình ROI · ▶ Phân tích · 📊 Xem kết quả · 🗑 Xoá.

### Flow: Thêm video (modal)

1. Click `+ Thêm video` → mở `<Dialog>`.
2. Form: tên (text) + file picker (drag & drop hoặc click).
3. Submit → `POST /api/sources` (multipart):
   - Hiển thị **upload progress bar** (XHR `progress` event).
   - Lock submit khi đang upload.
4. Success → đóng dialog, refetch list (TanStack Query invalidate).
5. Error → toast `Không thể thêm nguồn: <detail>`, giữ form.

> Khác với PyQt6: không có "chọn file local trên máy server" — luôn upload từ browser. Đây là thay đổi nghiệp vụ chính, chi tiết → [05-data-source-workflow.md](05-data-source-workflow.md).

### Flow: Xoá

Confirm dialog → `DELETE /api/sources/{id}` → invalidate.

---

## Page 2 — ROI Editor (`/sources/:id/roi`)

Đây là trang phức tạp nhất. Thay thế `roi_editor.py` PyQt6 bằng canvas-based editor.

### Wireframe

```
┌──────────────────────────────────────────────────────────────┐
│ ← Quay lại  |  ROI: Cam 1 - QL1                              │
├──────────────────────────────────────────┬───────────────────┤
│                                          │  Tools            │
│   ┌──────────────────────────────────┐   │  ○ Polygon (P)    │
│   │                                  │   │  ○ Line (L)       │
│   │      <FrameViewer + Canvas>      │   │  ○ Pan/Select (V) │
│   │      1920×1080 fitted            │   │                   │
│   │                                  │   │  Calibration      │
│   │      polygons + lines overlay    │   │  px/mét: [12.5  ] │
│   │                                  │   │                   │
│   │                                  │   │  Polygons (2)     │
│   └──────────────────────────────────┘   │  • lane_1  🗑     │
│                                          │  • lane_2  🗑     │
│   Time slice                             │                   │
│   [────●─────────────] 12.5s/300s        │  Lines (1)        │
│   [mm:ss: 00:12.5  ] [Go]                │  • count_in  🗑   │
│                                          │                   │
│   [Run Test Detection] [Save Frame]      │  [Save] [Reset]   │
└──────────────────────────────────────────┴───────────────────┘
```

### Tương tác canvas

- **Polygon mode:** click thêm điểm; double-click hoặc Enter đóng polygon. Esc huỷ polygon đang vẽ. Sau khi đóng, prompt nhập tên (default `lane_N`).
- **Line mode:** click 2 điểm tạo line; prompt tên + direction radio (`in`/`out`/`both`).
- **Pan/Select mode:** click trên shape để select; Delete xoá; drag điểm để chỉnh (optional, có thể defer phase sau).
- Phím tắt: `P` polygon, `L` line, `V` select, `Ctrl+S` save.

### Frame viewer

- Component `<FrameViewer>` lấy frame từ `GET /api/sources/{id}/frame?time=X`. Cache theo `time` qua TanStack Query (`staleTime: Infinity`).
- Slider sync với input `mm:ss`. Bấm `Go` mới fetch — không fetch on-the-fly khi kéo (tránh spam request).

### Run Test Detection

- `POST /api/sources/{id}/test-detect` với `{time, annotate: true}`.
- Loading spinner trong nút.
- Kết quả:
  - Thay frame hiển thị bằng `annotated_url`.
  - Panel phải hiện `summary` (bar chart đơn giản hoặc table 4 dòng).
  - **Performance panel** hiển thị `timings`:
    - `inference_ms` — thời gian YOLO forward + NMS
    - `fps_estimate` — ước lượng frame/giây model có thể xử lý (= 1000 / inference_ms)
    - `device` — thiết bị thực tế (cpu / cuda:0 / mps), giúp xác nhận GPU thực sự được dùng
    - `image_size` — kích thước frame
  - Banner gợi ý: nếu `inference_ms > 100` cảnh báo "Tốc độ chậm — cân nhắc giảm `imgsz` hoặc đổi sang `cuda:0`".
- Có nút "Quay lại frame gốc" để xoá overlay.

### Save Config

- Dồn state polygons + lines + px/m + reference_frame_index → `PUT /api/sources/{id}/roi`.
- Validate client-side: polygon ≥ 3 điểm, line đủ 2 điểm, px/m > 0 hoặc rỗng.

---

## Page 3 — Analysis (`/sources/:id/analysis`)

> **Lưu ý:** trang này chỉ phân tích batch trên video đã upload. Không có chế độ "live preview" hay "stream realtime". Nút Bắt đầu khởi chạy job đọc tuần tự video từ frame 0 đến hết.


### Wireframe

```
┌──────────────────────────────────────────────────────────────┐
│ ← Quay lại  |  Phân tích: Cam 1 - QL1                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Interval (giây): [30  ]                                     │
│  ☐ Render annotated video (.mp4) sau khi xong  ⓘ              │
│                                                              │
│  [▶ Bắt đầu phân tích]                                       │
│                                                              │
│  ── Đang chạy: sess_xyz ────────────────────────────────────│
│  Frames: 1234 / 9000  ████████░░░░░░░░░░░  13.7%            │
│  Interval hiện tại: 5    Elapsed: 02:14    ETA: 14:30        │
│  [✕ Huỷ]                                                     │
│                                                              │
│  ── Intervals (live) ───────────────────────────────────────│
│  | T   | car | mc | bus | truck | occ% | speed |             │
│  | 0:30| 12  | 45 | 1   | 2     | 0.35 | 28.5  |             │
│  | 1:00| 9   | 38 | 0   | 1     | 0.29 | 31.2  |             │
│  ...                                                          │
└──────────────────────────────────────────────────────────────┘
```

### Flow

1. Mount → kiểm tra `GET /api/sources/{id}/roi`. Nếu null → banner đỏ "Cần cấu hình ROI trước" + link sang Page 2.
2. Bấm Bắt đầu → `POST /api/sources/{id}/sessions` body `{interval_seconds, render_video}` → nhận `session_id`.
3. Mở WS `/ws/sessions/{session_id}` (custom hook `useSessionProgress`).
4. Render progress + append intervals đến khi nhận event `completed` / `failed` / `cancelled`.
5. Khi `completed`: hiển thị link "Xem & tải kết quả →" chuyển sang Page 4.
6. Nếu `render_video=true`: tiếp tục giữ WS để nhận event `artifact_ready` (kind=video) — UI hiển thị toast "Annotated video sẵn sàng" với link.
7. Nút Huỷ → `DELETE /api/sessions/{id}`; UI chờ event `cancelled`.

> Tooltip ⓘ cạnh checkbox render: "Sẽ tăng thời gian xử lý ~1.5–2× nhưng cho phép tải video đã annotate (bbox, track, ROI overlay) sau khi xong. Có thể tải sau từ Page Kết quả nếu không bật ngay."

### Hook design

```ts
function useSessionProgress(sessionId: string) {
  const [state, setState] = useState<{...}>(initial);
  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/sessions/${sessionId}`);
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      // dispatch by msg.type
    };
    ws.onclose = () => { /* attempt reconnect with backoff up to 3 times */ };
    return () => ws.close();
  }, [sessionId]);
  return state;
}
```

---

## Page 4 — Results (`/sources/:id/results`)

### Wireframe

```
┌────────────────────────────────────────────────────────────────────┐
│ ← Quay lại  |  Kết quả: Cam 1 - QL1                                │
├────────────────────────────────────────────────────────────────────┤
│  Session: [sess_xyz ▼]   Khoảng: [09:00 ─ 18:00]   [Áp dụng]      │
│                                                                    │
│  Tóm tắt: 12 intervals · Tổng xe 1247 · Avg occ 31% · ...          │
│                                                                    │
│  | T     | car | mc | bus | truck | occ% | speed |                 │
│  | 0:30  | 12  | 45 | 1   | 2     | 0.35 | 28.5  |                 │
│  ...                                                                │
│                                                                    │
│  ┌── Tải kết quả ───────────────────────────────────────────────┐  │
│  │  📄 result.csv          12.5 KB   [⬇ Tải]                     │  │
│  │  📊 summary.json        0.4 KB    [⬇ Tải]                     │  │
│  │  🎯 roi.json            0.2 KB    [⬇ Tải]                     │  │
│  │  🎬 annotated.mp4       205 MB    [⬇ Tải]  [▶ Xem]            │  │
│  │     ⏳ Đang render... (xuất hiện khi chưa xong)               │  │
│  │  ─────────────────────────────────────────────────            │  │
│  │  📦 [⬇ Tải tất cả (ZIP)]   ~217 MB                            │  │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  [▶ Preview annotated video]   (collapsible <video> element)       │
└────────────────────────────────────────────────────────────────────┘
```

### Flow

- Chọn session từ dropdown (`GET /api/sources/{id}/sessions`).
- Filter time range → `GET /api/sessions/{id}/intervals?start=&end=`.
- Tóm tắt tính client-side từ list interval.
- **Panel Tải kết quả:**
  - Fetch `GET /api/sessions/{id}/artifacts` khi chọn session.
  - Render danh sách: icon theo `kind`, name + size + mtime.
  - Nút "Tải" = `<a href={artifact.download_url} download>` — browser tự download (không cần JS fetch để giữ progress bar native + tránh OOM cho file lớn).
  - Annotated video có thêm nút "Xem" → toggle `<video src={preview_url} controls>` inline (range request cho phép seek).
  - **Nếu không có `video` artifact** + session đã hoàn tất: hiện nút **"Tạo video annotated"** → `POST /api/sessions/{id}/render-video` → status badge "Đang render..." → poll `GET /render-video` mỗi 3s hoặc subscribe WS chờ `artifact_ready` (kind=video).
  - Nút "Tải tất cả (ZIP)" = `<a href="/api/sessions/{id}/download/bundle.zip" download>`.
- **Trạng thái pending render:** nếu session vừa completed với `render_video=true` nhưng chưa có artifact `video` trong list:
  - Hiển thị placeholder "🎬 annotated.mp4 — ⏳ Đang render..."
  - Re-fetch `/artifacts` mỗi 5s đến khi có hoặc nhận event WS `artifact_ready` (nếu user vẫn ở Analysis tab session đó).
- **Trạng thái session chưa completed:** ẩn panel Tải, hiển thị "Phiên chưa hoàn tất, không có kết quả tải về."
- Optional: chart timeline (recharts) — defer nếu thiếu thời gian.

### Lưu ý kỹ thuật download

- **KHÔNG** dùng `fetch` + `Blob` cho file > 50MB → OOM tab. Dùng anchor link với `download` attribute.
- Với bundle ZIP có thể rất lớn (vài GB), browser sẽ stream xuống disk trực tiếp — không lo memory.
- Hiển thị toast "Bắt đầu tải ..." khi user click; không thể track progress chính xác từ browser khi dùng anchor (acceptable trade-off).
- Annotated video preview: dùng thuộc tính `<video preload="metadata">` để không kéo full file ngay khi mở panel.

---

## Page 5 — Inference Settings (`/settings/inference`)

> Thay thế hoàn toàn việc sửa `config/inference.yaml` bằng tay. Truy cập từ link "Inference Settings ⚙" trên TopBar.

### Wireframe

```
┌──────────────────────────────────────────────────────────────────┐
│  Inference Settings                                              │
│  ⓘ Thay đổi sẽ áp dụng cho phiên phân tích bắt đầu sau khi lưu.  │
│    Phiên đang chạy không bị ảnh hưởng.                            │
├──────────────────────────────────────────────────────────────────┤
│  ▼ Model                                                         │
│    Weights:    [yolo11m.pt ▼]   [↻ Rescan]                       │
│    Device:     ( ) Auto  ( ) CPU  (•) CUDA  ( ) MPS              │
│                CUDA index: [0]                                    │
│    Image size: [─────●────] 960    (320–1920, bội 32)             │
│    Half (FP16): [□] (chỉ NVIDIA GPU)                              │
│    Max det:    [1000]   Agnostic NMS: [□]                         │
│                                                                  │
│  ▼ Detection                                                     │
│    Confidence: [──●──────] 0.15                                  │
│    IoU:        [───●─────] 0.40                                  │
│    Classes:    [✓ car] [✓ motorcycle] [✓ bus] [✓ truck]           │
│                                                                  │
│  ▼ Detection ROI (crop trước khi detect)                         │
│    Enabled: [□]                                                  │
│    Bounds:   x_min [0.0] y_min [0.0] x_max [1.0] y_max [1.0]      │
│    [Preview trên frame mẫu ▾]   (defer-able)                     │
│                                                                  │
│  ▼ Tracking                                                      │
│    Activation threshold: [0.25]                                  │
│    Lost track buffer:    [30]                                    │
│    Min matching:         [0.80]                                  │
│    Min consecutive:      [3]                                     │
│                                                                  │
│  ▼ Speed                                                         │
│    Min frames: [5]                                               │
│                                                                  │
│  ▼ Analysis                                                      │
│    Default interval (s): [30]                                    │
│    Frame skip:           [1]   ⚠ >3 dễ vỡ tracker                │
│                                                                  │
│  ▼ Queue (xếp hàng)                                              │
│    Stopped speed (km/h): [5.0]                                   │
│    Window frames:        [5]                                     │
│                                                                  │
│  ▼ Vehicle PCE                                                   │
│    car:        [1.00]                                            │
│    motorcycle: [0.25]                                            │
│    bus:        [3.00]                                            │
│    truck:      [2.50]                                            │
│                                                                  │
│  [💾 Lưu]   [↺ Khôi phục mặc định]   [Huỷ thay đổi]               │
└──────────────────────────────────────────────────────────────────┘
```

### Flow

1. **Mount:** parallel fetch `GET /api/config/inference` + `GET /api/config/inference/schema` + `GET /api/system/models`.
2. Dựng form từ schema (label, mô tả, min/max, ui_hint). Mỗi section là `<details>` collapsible, mặc định mở.
3. Mỗi field có icon `?` hover → hiện `description` từ schema.
4. State: dùng react-hook-form với `defaultValues` = response từ GET.
5. **Validation client-side** (zod schema sync với Pydantic ở backend) — chặn submit nếu field invalid + highlight đỏ.
6. **Lưu:**
   - `PUT /api/config/inference` với toàn bộ form data.
   - 200 → toast success, refetch GET, reset form dirty state.
   - 400 → parse list lỗi, set field errors lên đúng field path (`model.imgsz`, `detection.confidence`, ...).
   - 503 (load weights fail) → toast lỗi cụ thể, **không** rollback (file YAML đã lưu — đây là quyết định: ưu tiên persist, user phải sửa lại).
7. **Khôi phục mặc định:** confirm dialog → `POST /api/config/inference/reset` → refetch.
8. **Huỷ thay đổi:** form reset về defaultValues (không gọi API).
9. Khi rời trang nếu form dirty → confirm "Bạn có thay đổi chưa lưu, tiếp tục?".

### Component breakdown

```
InferenceSettingsPage
├── ConfigSection (collapsible)            # × 8 sections
│   └── ConfigField (theo schema metadata)
│       ├── NumberInput (slider + input số đồng bộ)
│       ├── SelectInput (cho weights, device)
│       ├── CheckboxInput (cho boolean)
│       ├── BoundsInput (cho detection_roi.bounds)
│       └── ChipsInput (cho class_ids)
├── SaveBar (sticky bottom): Lưu / Reset / Huỷ
└── DirtyGuard (router prompt khi dirty)
```

### Khác biệt so với sửa YAML thủ công

| Aspect | YAML thủ công | UI Inference Settings |
|---|---|---|
| Cần SSH/exec container | Có | Không |
| Validate trước khi áp | Không (lỗi xảy ra runtime) | Có (client + server) |
| Mô tả tham số | Đọc comment trong YAML | Hiện inline qua tooltip |
| Khôi phục default | Tự xoá / giữ git copy | 1 click |
| Áp dụng | Restart process | Hot-reload Container |
| Risk sai chính tả YAML | Có | Không (form structured) |

---

## Component map

```
src/
├── api/
│   ├── client.ts         # fetch wrapper, error handling
│   ├── sources.ts        # listSources, addSource, deleteSource, ...
│   ├── roi.ts            # getRoi, putRoi
│   ├── sessions.ts       # startSession, getSession, getIntervals, ...
│   ├── artifacts.ts      # [NEW] listArtifacts, downloadUrl(kind), bundleUrl
│   ├── inference.ts      # [NEW] getConfig, putConfig, resetConfig, getSchema, listModels
│   └── ws.ts             # SessionWebSocket class
├── components/
│   ├── ROICanvas.tsx
│   ├── FrameViewer.tsx
│   ├── VideoUploader.tsx
│   ├── ProgressBar.tsx
│   ├── SystemMonitorPill.tsx
│   ├── ConfirmDialog.tsx
│   ├── ArtifactList.tsx  # [NEW] panel "Tải kết quả"
│   ├── VideoPreview.tsx  # [NEW] inline <video> với range request
│   └── ConfigForm/       # [NEW]
│       ├── ConfigSection.tsx
│       ├── ConfigField.tsx
│       ├── NumberInput.tsx
│       ├── BoundsInput.tsx
│       ├── ChipsInput.tsx
│       └── DirtyGuard.tsx
├── hooks/
│   ├── useSessionProgress.ts
│   ├── useChunkedUpload.ts (optional)
│   └── useInferenceConfig.ts  # [NEW] wrap query + mutation
├── pages/
│   ├── SourcesPage.tsx
│   ├── ROIEditorPage.tsx
│   ├── AnalysisPage.tsx
│   ├── ResultsPage.tsx
│   └── InferenceSettingsPage.tsx  # [NEW]
└── App.tsx (Layout + Router)
```

## Accessibility & i18n

- Tất cả button có `aria-label`.
- Hỗ trợ tiếng Việt mặc định (giữ wording theo PyQt6 cũ); chuẩn bị structure i18n (`react-i18next`) nhưng có thể defer việc thêm tiếng Anh.
- Keyboard shortcut tài liệu hoá trong popup `?` ở topbar.

## Responsive

- Min width hỗ trợ: 1280×720 (desktop). Mobile không bắt buộc — ROI editor không khả thi trên touch nhỏ.
- Responsive table: scroll horizontal trên < 1024px.
