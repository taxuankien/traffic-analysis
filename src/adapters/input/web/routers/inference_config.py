"""Inference config: GET / PUT / reset / schema metadata.

Backend cho UI ``InferenceSettingsPage`` thay thế việc sửa ``inference.yaml``
thủ công. Validate qua Pydantic; persist qua ``InferenceConfigRepositoryPort``;
hot-reload qua ``Container.reload_inference_config()``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.adapters.input.web.deps import get_container
from src.adapters.input.web.schemas.inference_config import (
    AnalysisSection,
    DetectionROISection,
    DetectionSection,
    FieldMeta,
    InferenceConfigDTO,
    ModelFileInfo,
    ModelSection,
    QueueSection,
    SpeedSection,
    TrackingSection,
    VehiclePCESection,
)
from src.bootstrap.container import Container
from src.bootstrap.inference_config import (
    AnalysisConfig,
    DetectionConfig,
    DetectionROIConfig,
    InferenceConfig,
    ModelConfig,
    QueueConfig,
    SpeedConfig,
    TrackingConfig,
    VehiclePCEConfig,
)

router = APIRouter(prefix="/config/inference", tags=["inference-config"])
logger = logging.getLogger(__name__)


def _config_to_dto(cfg: InferenceConfig) -> InferenceConfigDTO:
    return InferenceConfigDTO(
        model=ModelSection(
            weights=cfg.model.weights,
            device=cfg.model.device,
            imgsz=cfg.model.imgsz,
            half=cfg.model.half,
            max_det=cfg.model.max_det,
            agnostic_nms=cfg.model.agnostic_nms,
        ),
        detection=DetectionSection(
            confidence=cfg.detection.confidence,
            iou=cfg.detection.iou,
            class_ids=list(cfg.detection.class_ids),
        ),
        detection_roi=DetectionROISection(
            enabled=cfg.detection_roi.enabled,
            bounds=tuple(cfg.detection_roi.bounds),  # type: ignore[arg-type]
        ),
        tracking=TrackingSection(
            track_activation_threshold=cfg.tracking.track_activation_threshold,
            lost_track_buffer=cfg.tracking.lost_track_buffer,
            minimum_matching_threshold=cfg.tracking.minimum_matching_threshold,
            minimum_consecutive_frames=cfg.tracking.minimum_consecutive_frames,
        ),
        speed=SpeedSection(min_frames=cfg.speed.min_frames),
        analysis=AnalysisSection(
            default_interval_seconds=cfg.analysis.default_interval_seconds,
            frame_skip=cfg.analysis.frame_skip,
        ),
        queue=QueueSection(
            stopped_speed_kmh=cfg.queue.stopped_speed_kmh,
            window_frames=cfg.queue.window_frames,
        ),
        vehicle_pce=VehiclePCESection(
            car=cfg.vehicle_pce.car,
            motorcycle=cfg.vehicle_pce.motorcycle,
            bus=cfg.vehicle_pce.bus,
            truck=cfg.vehicle_pce.truck,
        ),
    )


def _dto_to_config(dto: InferenceConfigDTO) -> InferenceConfig:
    return InferenceConfig(
        model=ModelConfig(
            weights=dto.model.weights,
            device=dto.model.device,
            imgsz=dto.model.imgsz,
            half=dto.model.half,
            max_det=dto.model.max_det,
            agnostic_nms=dto.model.agnostic_nms,
        ),
        detection=DetectionConfig(
            confidence=dto.detection.confidence,
            iou=dto.detection.iou,
            class_ids=list(dto.detection.class_ids),
        ),
        detection_roi=DetectionROIConfig(
            enabled=dto.detection_roi.enabled,
            bounds=list(dto.detection_roi.bounds),
        ),
        tracking=TrackingConfig(
            track_activation_threshold=dto.tracking.track_activation_threshold,
            lost_track_buffer=dto.tracking.lost_track_buffer,
            minimum_matching_threshold=dto.tracking.minimum_matching_threshold,
            minimum_consecutive_frames=dto.tracking.minimum_consecutive_frames,
        ),
        speed=SpeedConfig(min_frames=dto.speed.min_frames),
        analysis=AnalysisConfig(
            default_interval_seconds=dto.analysis.default_interval_seconds,
            frame_skip=dto.analysis.frame_skip,
        ),
        queue=QueueConfig(
            stopped_speed_kmh=dto.queue.stopped_speed_kmh,
            window_frames=dto.queue.window_frames,
        ),
        vehicle_pce=VehiclePCEConfig(
            car=dto.vehicle_pce.car,
            motorcycle=dto.vehicle_pce.motorcycle,
            bus=dto.vehicle_pce.bus,
            truck=dto.vehicle_pce.truck,
        ),
    )


@router.get("", response_model=InferenceConfigDTO)
def get_inference_config(container: Container = Depends(get_container)) -> InferenceConfigDTO:
    return _config_to_dto(container.inference_config)


@router.put("", response_model=InferenceConfigDTO)
def put_inference_config(
    body: InferenceConfigDTO,
    container: Container = Depends(get_container),
) -> InferenceConfigDTO:
    try:
        new_cfg = _dto_to_config(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    repo = container.inference_config_repo()
    try:
        repo.save(new_cfg)
    except OSError as exc:
        raise HTTPException(500, f"Không ghi được file config: {exc}") from exc

    container.reload_inference_config(new_cfg)
    logger.info("Inference config đã cập nhật và hot-reload.")
    return _config_to_dto(new_cfg)


@router.post("/reset", response_model=InferenceConfigDTO, status_code=status.HTTP_200_OK)
def reset_inference_config(container: Container = Depends(get_container)) -> InferenceConfigDTO:
    repo = container.inference_config_repo()
    defaults = repo.reset_to_defaults()
    container.reload_inference_config(defaults)
    return _config_to_dto(defaults)


@router.get("/schema", response_model=dict[str, FieldMeta])
def get_inference_schema() -> dict[str, FieldMeta]:
    """Metadata cho UI form: label, mô tả, range, ui_hint.

    Khoá theo dot-path để frontend match đúng field. Đây không phải JSON Schema
    thuần — purpose-built cho form rendering.
    """
    return _SCHEMA_METADATA


_SCHEMA_METADATA: dict[str, FieldMeta] = {
    "model.weights": FieldMeta(
        type="string",
        label="YOLO weights",
        description="Path tới file .pt (tương đối models dir hoặc tuyệt đối). Có thể chọn từ dropdown /api/system/models.",
        ui_hint="model_picker",
    ),
    "model.device": FieldMeta(
        type="select",
        label="Device",
        description="null = auto. Chọn 'cpu', 'cuda', 'cuda:0', hoặc 'mps'.",
        options=["", "cpu", "cuda", "cuda:0", "mps"],
        default=None,
    ),
    "model.imgsz": FieldMeta(
        type="integer",
        label="Image size",
        description="Kích thước ảnh inference (bội số 32). Tăng 1280/1920 cho video độ phân giải thấp / object nhỏ.",
        min=320, max=1920, step=32, default=960,
    ),
    "model.half": FieldMeta(
        type="boolean",
        label="Half precision (FP16)",
        description="Bật khi có GPU NVIDIA — tăng tốc độ, giảm độ chính xác chút.",
        default=False,
    ),
    "model.max_det": FieldMeta(
        type="integer",
        label="Max detections per frame",
        description="Tăng 500–1000 cho VN giờ cao điểm (xe máy đông).",
        min=1, max=10000, step=1, default=1000,
    ),
    "model.agnostic_nms": FieldMeta(
        type="boolean",
        label="Agnostic NMS",
        description="NMS xuyên class; thường giữ false.",
        default=False,
    ),
    "detection.confidence": FieldMeta(
        type="number",
        label="Confidence threshold",
        description="Ngưỡng tin cậy. Giảm 0.15–0.20 cho video mờ / xe máy bị che.",
        min=0.0, max=1.0, step=0.01, default=0.15,
    ),
    "detection.iou": FieldMeta(
        type="number",
        label="IoU (NMS)",
        description="Giảm 0.5–0.6 cho cảnh đông để bớt suppress nhầm.",
        min=0.0, max=1.0, step=0.05, default=0.4,
    ),
    "detection.class_ids": FieldMeta(
        type="string_list",
        label="COCO class IDs",
        description="2=car, 3=motorcycle, 5=bus, 7=truck.",
    ),
    "detection_roi.enabled": FieldMeta(
        type="boolean", label="Detection ROI enabled",
        description="Bật để crop frame trước khi đưa vào YOLO; giảm khối lượng tính toán.",
    ),
    "detection_roi.bounds": FieldMeta(
        type="string_list", label="Detection ROI bounds [x_min, y_min, x_max, y_max]",
        description="Toạ độ chuẩn hoá [0.0, 1.0]. Ví dụ cắt 20% trên + 10% dưới: [0, 0.2, 1, 0.9].",
    ),
    "tracking.track_activation_threshold": FieldMeta(
        type="number", label="Track activation threshold",
        min=0.0, max=1.0, step=0.05, default=0.25,
    ),
    "tracking.lost_track_buffer": FieldMeta(
        type="integer", label="Lost track buffer (frames)",
        description="Tăng 45–60 cho VN (xe máy luồn lách).",
        min=0, step=1, default=30,
    ),
    "tracking.minimum_matching_threshold": FieldMeta(
        type="number", label="Min matching threshold",
        description="Giảm 0.6–0.7 cho object nhỏ chuyển động nhanh.",
        min=0.0, max=1.0, step=0.05, default=0.8,
    ),
    "tracking.minimum_consecutive_frames": FieldMeta(
        type="integer", label="Min consecutive frames", min=1, step=1, default=3,
    ),
    "speed.min_frames": FieldMeta(
        type="integer", label="Speed min frames",
        description="Track ngắn hơn ngưỡng này bị loại khỏi tính vận tốc.",
        min=1, step=1, default=5,
    ),
    "analysis.default_interval_seconds": FieldMeta(
        type="number", label="Default interval (s)",
        min=1.0, step=1.0, default=30.0,
    ),
    "analysis.frame_skip": FieldMeta(
        type="integer", label="Frame skip",
        description="1 = mọi frame; >3 dễ vỡ tracker.",
        min=1, max=10, step=1, default=1,
    ),
    "queue.stopped_speed_kmh": FieldMeta(
        type="number", label="Stopped speed (km/h)",
        description="Vận tốc tối đa coi là đang xếp hàng.",
        min=0.1, step=0.5, default=5.0,
    ),
    "queue.window_frames": FieldMeta(
        type="integer", label="Queue window frames",
        min=2, step=1, default=5,
    ),
    "vehicle_pce.car": FieldMeta(type="number", label="PCE car", min=0.01, step=0.05, default=1.0),
    "vehicle_pce.motorcycle": FieldMeta(
        type="number", label="PCE motorcycle",
        description="Chuẩn VN 0.25–0.30 (TCVN 4054).", min=0.01, step=0.05, default=0.3,
    ),
    "vehicle_pce.bus": FieldMeta(type="number", label="PCE bus", min=0.01, step=0.1, default=3.0),
    "vehicle_pce.truck": FieldMeta(type="number", label="PCE truck", min=0.01, step=0.1, default=2.5),
}


# --- Models list endpoint (lives here for thematic grouping) -----------------


@router.get("/models", include_in_schema=False)
def _placeholder() -> None:  # pragma: no cover
    raise HTTPException(404, "Use /api/system/models")
