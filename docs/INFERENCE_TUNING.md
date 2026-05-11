# Hướng dẫn tinh chỉnh tham số mô hình

Tài liệu này giải thích từng tham số trong [config/inference.yaml](../config/inference.yaml) và đề xuất cách điều chỉnh cho các tình huống điển hình của giao thông Việt Nam (video độ phân giải thấp, mật độ xe máy cao).

---

## 1. Tổng quan

Mọi tham số ảnh hưởng tới chất lượng dự đoán đều nằm trong **một file YAML duy nhất**: `config/inference.yaml`. File này được load tự động khi:

- Chạy GUI: `python -m src.adapters.input.gui.app` (hoặc `run.bat`).
- Chạy CLI: `python -m src.adapters.input.cli.main_cli <command>`.

### Thứ tự ưu tiên khi tìm file cấu hình

1. Tham số `--config <PATH>` của CLI (cao nhất).
2. Biến môi trường `TRAFFIC_INFERENCE_CONFIG=<PATH>`.
3. `config/inference.yaml` ở project root (mặc định).
4. Nếu không có file nào → dùng giá trị default trong code (đồng bộ với YAML mặc định).

### Validation

Loader **fail-fast**: ngay khi gặp giá trị sai miền (vd `confidence: 1.5`) hoặc key lạ (vd `confidance:` do typo) sẽ raise `ValueError` với message tiếng Việt nêu rõ field nào, giá trị nhận được, miền hợp lệ. Key thiếu sẽ dùng default + log INFO (không lỗi).

---

## 2. Bảng tham số

### 2.1 `model` — model loader & inference engine

| Key | Default | Miền | Ý nghĩa | Ảnh hưởng |
|---|---|---|---|---|
| `weights` | `models/yolo11x.pt` | path .pt | Trọng số YOLO. Lớn (`x`) → recall cao + chậm; nhỏ (`n`, `s`) → nhanh + miss object nhỏ | Đổi model = đổi cả tốc độ và độ chính xác |
| `device` | `null` (auto) | `null`, `"cpu"`, `"cuda:0"`, `"mps"` | Thiết bị inference | `cpu` chậm hơn GPU 10–50× |
| `imgsz` | `640` | bội số 32 ≥ 32 | Kích thước ảnh đưa vào model (sẽ resize về cạnh dài này) | **Tăng → vớt object nhỏ tốt hơn** nhưng VRAM + thời gian tăng theo bình phương |
| `half` | `false` | bool | FP16 inference | Bật trên GPU NVIDIA → tăng tốc ~30–50%, giảm độ chính xác không đáng kể |
| `max_det` | `300` | số nguyên dương | Số detection tối đa trả về cho mỗi frame | **Phải > số xe thực tế trong khung hình** — nếu không sẽ truncate xe ở rìa |
| `agnostic_nms` | `false` | bool | NMS không phân biệt class | `true` → nguy cơ ô tô nuốt mất xe máy chồng lấn; **giữ false cho VN** |

### 2.2 `detection` — detector thresholds

| Key | Default | Miền | Ý nghĩa | Ảnh hưởng |
|---|---|---|---|---|
| `confidence` | `0.25` | `[0.0, 1.0]` | Ngưỡng tin cậy tối thiểu để giữ detection | **Giảm → recall ↑, precision ↓**. Object mờ thường có conf < 0.25 |
| `iou` | `0.7` | `[0.0, 1.0]` | Ngưỡng IoU cho NMS (Non-Max Suppression) | **Giảm → ít suppress nhầm hơn** khi xe sát nhau (như VN giờ cao điểm) |
| `class_ids` | `[2, 3, 5, 7]` | list COCO IDs | Chỉ giữ detection thuộc các class này | Bỏ class không cần (vd chỉ đếm xe máy: `[3]`) → bớt false positive |

### 2.3 `detection_roi` — vùng cần detect (giảm khối lượng tính toán)

Phần này định nghĩa **vùng chữ nhật** trên khung hình mà model thực sự cần xử lý. Khi bật, frame sẽ được **crop trước khi đưa vào YOLO**, nên thời gian inference giảm tỉ lệ với diện tích bị cắt bỏ. Toạ độ bbox mà detector trả về được dịch tự động về toạ độ frame gốc, do đó:

- Polygon ROI / counting line / occupancy zone (đã vẽ trong GUI ROI Editor) **giữ nguyên** — không cần chỉnh.
- Annotated render vẫn dùng frame gốc (vùng ngoài crop hiển thị bình thường nhưng không có detection).

| Key | Default | Miền | Ý nghĩa |
|---|---|---|---|
| `enabled` | `false` | bool | `false` = detect toàn khung hình (hành vi cũ); `true` = chỉ detect trong `bounds` |
| `bounds` | `[0.0, 0.0, 1.0, 1.0]` | 4 số thực `[x_min, y_min, x_max, y_max]` trong `[0.0, 1.0]` | Toạ độ chuẩn hoá (gốc trên-trái = `0,0`, dưới-phải = `1,1`). Bắt buộc `x_min < x_max` và `y_min < y_max`. |

**Vì sao chuẩn hoá thay vì pixel?** Cùng một file config dùng được cho mọi độ phân giải video (480p, 720p, 1080p, 4K) — chỉ phụ thuộc vào bố cục camera, không phụ thuộc kích thước frame.

**Cách xác định `bounds` nhanh nhất:**
1. Mở 1 frame mẫu trong GUI ROI Editor (hoặc bất kỳ image viewer nào hiển thị toạ độ chuột).
2. Đọc toạ độ `(x, y)` ở 4 đỉnh của vùng đường bộ thực sự cần detect.
3. Chia cho `width` và `height` của frame để ra giá trị `[0.0, 1.0]`.

**Hoặc vẽ trực tiếp trong GUI** (xem §4) — không cần tính toạ độ thủ công, không cần sửa YAML.

**Ví dụ thực tế:**

```yaml
detection_roi:
  enabled: true
  # Camera đặt cao, phần trên là trời/mái nhà (không có xe), phần dưới là vỉa hè.
  # Cắt bỏ 25% trên + 10% dưới → còn lại 65% chiều cao cần detect.
  bounds: [0.0, 0.25, 1.0, 0.90]
```

```yaml
detection_roi:
  enabled: true
  # Camera nhìn 1 chiều đường bên phải, làn bên trái không quan tâm.
  bounds: [0.45, 0.20, 1.0, 1.0]
```

**Đo lường hiệu năng:** thời gian inference của YOLO tỉ lệ ~ tuyến tính với số pixel sau khi đã resize về `imgsz`. Nếu ROI giữ ~50% diện tích, inference nhanh hơn ~30–45% (không phải 50% vì YOLO vẫn resize cạnh dài về `imgsz`). ROI càng dẹt theo 1 chiều, lợi thế tốc độ càng rõ vì cạnh dài crop ngắn hơn.

**Lưu ý phối hợp với `model.imgsz`:** sau khi crop, frame nhỏ lại nhưng vẫn được resize về `imgsz`. Vì vậy nếu mục tiêu là **vớt object nhỏ ở xa**, có thể giảm `imgsz` xuống (vd `640` → `960`) và bật `detection_roi` để đạt độ chi tiết tương đương `imgsz: 1280` mà nhanh hơn.

**Cảnh báo biên:** xe ngay tại biên ROI có thể bị cắt mất 1 phần bbox dẫn tới detection lệch. Để biên độ an toàn, chừa thêm ~5% mỗi cạnh so với vùng đường thực tế.

### 2.4 `tracking` — ByteTrack

| Key | Default | Miền | Ý nghĩa | Ảnh hưởng |
|---|---|---|---|---|
| `track_activation_threshold` | `0.25` | `[0.0, 1.0]` | Conf tối thiểu để bắt đầu track mới | Đồng bộ với `detection.confidence` |
| `lost_track_buffer` | `30` | ≥ 0 | Số frame giữ track sau khi mất detection | **Tăng → ít mất ID** khi object bị che tạm thời (xe máy bị ô tô che ở VN); tăng quá → ID giả khi object ra khỏi khung hình |
| `minimum_matching_threshold` | `0.8` | `[0.0, 1.0]` | IoU giữa detection mới và track cũ để gán | **Giảm → gán dễ hơn** cho object nhỏ chuyển động nhanh (xe máy tốc độ cao); giảm quá → ID bị tráo |
| `minimum_consecutive_frames` | `3` | ≥ 1 | Số frame liên tiếp để xác nhận track | **Giảm → ít miss track ngắn**; giảm quá → nhiều ID giả do flicker |

### 2.5 `speed` — SpeedEstimator

| Key | Default | Miền | Ý nghĩa | Ảnh hưởng |
|---|---|---|---|---|
| `min_frames` | `5` | ≥ 1 | Track tồn tại < ngưỡng này bị loại khỏi tính vận tốc | Giảm → mẫu nhiều hơn nhưng nhiễu hơn; tăng → mẫu ổn định nhưng có thể bỏ qua xe đi nhanh qua khung |

### 2.6 `analysis` — pipeline

| Key | Default | Miền | Ý nghĩa |
|---|---|---|---|
| `default_interval_seconds` | `30.0` | > 0 | Độ dài 1 interval khi GUI/CLI không truyền giá trị riêng |

### 2.7 `vehicle_pce` — Passenger Car Equivalent

PCE dùng để quy đổi các loại xe về đơn vị "xe con" khi tính lưu lượng & độ chiếm dụng. Default đã chỉnh theo TCVN 4054 (chuẩn VN).

| Key | Default (VN) | Chuẩn HCM (US) | Ghi chú |
|---|---|---|---|
| `car` | `1.0` | `1.0` | Đơn vị tham chiếu |
| `motorcycle` | **`0.3`** | `0.5` | VN: dòng xe máy đông + linh hoạt → tỷ lệ xếp chồng làn nhỏ hơn |
| `bus` | `3.0` | `2.0–3.0` | |
| `truck` | `2.5` | `2.0–2.5` | |

---

## 3. Tinh chỉnh theo tình huống

### 3.1 Video độ phân giải thấp / nhiễu / CCTV cũ

Triệu chứng: bbox nhấp nháy, miss xe ở xa, count thấp bất thường, xe máy gần như không được phát hiện.

```yaml
model:
  weights: "models/yolo11x.pt"   # GIỮ model lớn, không downsize
  imgsz: 1280                     # hoặc 1920 nếu GPU đủ — quan trọng nhất
  half: true                      # bù tốc độ khi tăng imgsz (chỉ GPU NVIDIA)

detection:
  confidence: 0.18                # default 0.25 sẽ miss object mờ
  iou: 0.6                        # giảm nhẹ vì bbox kém chính xác

tracking:
  track_activation_threshold: 0.18
  minimum_consecutive_frames: 2   # track hay nhấp nháy do mờ
  lost_track_buffer: 45           # tăng để chịu được vài frame thiếu
```

**Cảnh báo throughput:** `imgsz: 1280` tốn ~4× VRAM và tăng thời gian inference ~2.5× so với `640`. Trên CPU sẽ rất chậm — nếu bắt buộc CPU, chỉ tăng `imgsz` lên `960` và đổi sang `yolov8s.pt`.

### 3.2 Mật độ xe máy cao (giao thông Việt Nam)

Triệu chứng: nhiều xe máy bị NMS nuốt mất, count thấp, ID nhảy liên tục khi xe luồn lách qua nhau.

```yaml
model:
  max_det: 1000                   # nút giao VN giờ cao điểm có thể >300 xe/frame
  agnostic_nms: false             # GIỮ false để class-aware NMS không nuốt xe máy

detection:
  confidence: 0.20                # xe máy hay bị che một phần
  iou: 0.55                       # KEY — default 0.7 suppress quá tay khi xe máy sát nhau

tracking:
  lost_track_buffer: 60           # xe máy chui qua sau ô tô và xuất hiện lại
  minimum_matching_threshold: 0.65  # IoU giữa frame của object nhỏ + nhanh thường thấp
  minimum_consecutive_frames: 2   # tránh drop track ngắn

vehicle_pce:
  motorcycle: 0.25                # khu phố cũ thuần xe máy (HN cổ, Q1 HCM); quốc lộ thì giữ 0.30
```

**Vì sao giảm `iou` quan trọng nhất?** Ở VN xe máy đi sát nhau với khoảng cách <0.5m. Bbox của 2 xe máy cạnh nhau có IoU 0.5–0.6 — với ngưỡng default `0.7`, NMS sẽ giữ cả 2; nhưng nếu detector cho ra 3-4 box cùng vùng (1 cho từng xe + 1 box bao cả cụm), ngưỡng `0.7` sẽ giữ box bao và nuốt từng xe. Giảm xuống `0.55` ép NMS suppress mạnh hơn các box trùng cụm.

### 3.3 Giảm thời gian inference khi camera có vùng "vô dụng" lớn

Triệu chứng: camera đặt cao/lệch nên >30% khung hình là trời, mái nhà, vỉa hè, hoặc làn ngược chiều không quan tâm; frame rate analyser thấp dù GPU dư.

```yaml
detection_roi:
  enabled: true
  # Đo trước trên 1 frame: vùng đường thực tế chỉ chiếm 60% chiều cao + 80% chiều ngang.
  bounds: [0.10, 0.25, 0.90, 0.85]
```

Có thể kết hợp với `model.imgsz` nhỏ hơn để bù lại độ chi tiết:

```yaml
model:
  imgsz: 960     # giảm từ 1280 — sau khi crop, vùng cần detect vẫn được phóng lên 960 nên độ chi tiết tương đương
  half: true

detection_roi:
  enabled: true
  bounds: [0.10, 0.25, 0.90, 0.85]
```

**Đo trước/sau:** dùng nút **Run Test Detection** trong GUI hoặc CLI `analyze` với cùng 1 đoạn video — so sánh `elapsed_seconds` ở progress callback. Kỳ vọng giảm 25–45% tuỳ tỉ lệ crop.

### 3.4 Combo VN thực tế (CCTV độ phân giải thấp + xe máy đông)

Dùng cho hầu hết camera giao thông VN hiện hữu (camera CSGT, bảng thông tin):

```yaml
model:
  weights: "models/yolo11x.pt"
  imgsz: 1280
  half: true                      # nếu có GPU NVIDIA
  max_det: 1000

detection:
  confidence: 0.18
  iou: 0.55

tracking:
  track_activation_threshold: 0.18
  lost_track_buffer: 60
  minimum_matching_threshold: 0.65
  minimum_consecutive_frames: 2

vehicle_pce:
  motorcycle: 0.25
```

**Đánh đổi:** chậm hơn ~3× so với default. Chấp nhận được cho phân tích batch offline; không phù hợp cho real-time monitoring trừ khi có GPU mạnh (RTX 3060 trở lên).

---

## 4. Cấu hình Detection ROI từ giao diện (GUI)

Mỗi source video có thể lưu **Detection ROI riêng** — không cần chỉnh `inference.yaml` nữa. Bounds vẽ ở GUI lưu cùng với polygon/line trong file `data/configs/<source_id>.json` và **override** giá trị mặc định trong YAML khi chạy session, render hoặc test detection cho source đó.

### 4.1 Thứ tự ưu tiên

Khi chạy detection, hệ thống chọn ROI theo thứ tự:

1. **`ROIConfig.detection_roi` của source** (vẽ trong GUI) — nếu đã lưu, dùng giá trị này.
2. **`detection_roi` trong `inference.yaml`** — nếu source chưa cấu hình riêng, fallback về YAML.
3. **Toàn khung hình** — nếu cả hai đều không có (hoặc YAML có `enabled: false`).

Tắt ROI cho 1 source cụ thể (trong khi YAML đang bật): vào ROI Editor → bấm **Xoá** trong nhóm "Detection ROI" → **Lưu config**.

### 4.2 Quy trình vẽ trong ROI Editor

1. Mở source trong **ROI Editor**.
2. Trượt slider tới 1 frame đại diện (có nhiều phương tiện).
3. Trong panel bên phải, mục **Detection ROI (vùng cần detect)**: bấm **Vẽ Detection ROI (click 2 góc)**.
4. Click 2 lần trên canvas: góc trên-trái → góc dưới-phải. Hệ thống tự sắp xếp toạ độ nên click theo thứ tự nào cũng được.
5. Hình chữ nhật xanh dương hiện ra; label hiển thị `Bounds (chuẩn hoá): [x1, y1, x2, y2]` để xác nhận.
6. Bấm **Run Test Detection** để xem ngay hiệu quả — chỉ vùng trong hình vuông được detect, vùng ngoài bị bỏ qua hoàn toàn.
7. Lặp bước 3–6 nếu cần điều chỉnh; bấm **Xoá** để xoá và vẽ lại.
8. Bấm **Lưu config** để persist.

### 4.3 Test detection phản ánh ROI ngay (không cần lưu)

Khi nhấn **Run Test Detection**, vùng ROI hiện đang vẽ (kể cả chưa lưu) được áp dụng cho lần detect đó — tiện cho việc thử-sai nhiều biên độ trước khi commit.

### 4.4 Lưu ý

- Toạ độ lưu dưới dạng **chuẩn hoá** trong JSON, vẫn hợp lệ nếu đổi độ phân giải video sau này (chỉ cần aspect ratio không đổi).
- ROI vẽ trong GUI **không thay thế** polygon ROI dùng cho counting/zone — đó là 2 lớp độc lập:
  - **Detection ROI (rectangle xanh dương)**: cắt frame trước khi đưa vào YOLO → giảm compute.
  - **Polygon ROI (xanh lá / đỏ trong render)**: vùng tính occupancy/queue *sau* khi đã detect.
- Polygon ROI và counting line nên nằm **bên trong** Detection ROI — nếu phần lớn polygon nằm ngoài ROI, sẽ không có detection nào để đếm.

---

## 5. Quy trình tinh chỉnh đề xuất

Khi nhận một video mới, làm tuần tự:

1. **Baseline.** Chạy với `config/inference.yaml` mặc định, dùng nút **Run Test Detection** trong GUI (ROI Editor) trên 2–3 frame đại diện của video (thưa, vừa, đông).

2. **Kiểm tra recall** (có thiếu xe không?). Đếm tay số xe trong frame test → so với detection thực tế.
   - Thiếu nhiều xe nhỏ/mờ → **tăng `model.imgsz`** lên `1280`.
   - Vẫn thiếu → **giảm `detection.confidence`** xuống `0.18–0.20`.

3. **Kiểm tra precision** (có double-count không?). Quan sát preview/render xem có 2 box trùng lên 1 xe không.
   - Có → **tăng `detection.iou`** lên `0.75–0.8`.
   - 1 ô tô nuốt motorcycle gần đó (xảy ra khi `agnostic_nms: true`) → đặt lại `false`.
   - Cụm xe máy chỉ ra 1 box bao → **giảm `detection.iou`** về `0.55`.

4. **Kiểm tra tracking** (ID có nhảy không?). Xem video annotated `render` → quan sát track ID.
   - ID nhảy khi xe bị che → **tăng `tracking.lost_track_buffer`** lên `45–60`.
   - Track xuất hiện rồi biến mất quá nhanh → **giảm `tracking.minimum_consecutive_frames`** từ `3` xuống `2`.
   - Track của xe đi nhanh đứt giữa chừng → **giảm `tracking.minimum_matching_threshold`** từ `0.8` xuống `0.65`.

5. **Lưu preset.** Khi đã tinh chỉnh ổn cho 1 loại camera, lưu thành file riêng: `config/inference_camera_giaolo3.yaml` và chạy với `--config <path>` để khỏi sửa file mặc định.

---

## 6. Tham chiếu

- Ultralytics predict params: <https://docs.ultralytics.com/modes/predict/#inference-arguments>
- Supervision ByteTrack: <https://supervision.roboflow.com/latest/trackers/>
- TCVN 4054:2005 (Đường ô tô — yêu cầu thiết kế): tham khảo PCE chuẩn VN cho xe máy.
