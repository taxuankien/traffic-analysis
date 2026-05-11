"""Pydantic schemas mirror cấu trúc ``InferenceConfig`` (dataclass).

Mirror thay vì wrap để: (a) FastAPI auto-generate OpenAPI; (b) validation
chạy ở Pydantic boundary, không phải post-init dataclass — giúp 400 trả
``loc/msg`` chuẩn FastAPI thay vì plain ValueError.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ModelSection(BaseModel):
    weights: str
    device: str | None = None
    imgsz: int = Field(960, ge=320, le=1920)
    half: bool = False
    max_det: int = Field(1000, ge=1)
    agnostic_nms: bool = False

    @field_validator("imgsz")
    @classmethod
    def _imgsz_multiple_of_32(cls, v: int) -> int:
        if v % 32 != 0:
            raise ValueError("imgsz phải là bội số của 32 (ví dụ 320, 640, 960, 1280, 1920)")
        return v

    @field_validator("device")
    @classmethod
    def _device_format(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip().lower()
        if s == "":
            return None
        if s in {"cpu", "cuda", "mps"} or s.startswith("cuda:"):
            return s
        raise ValueError("device phải là null | 'cpu' | 'cuda' | 'cuda:N' | 'mps'")


class DetectionSection(BaseModel):
    confidence: float = Field(0.15, ge=0.0, le=1.0)
    iou: float = Field(0.4, ge=0.0, le=1.0)
    class_ids: list[int] = Field(default_factory=lambda: [2, 3, 5, 7], min_length=1)


class DetectionROISection(BaseModel):
    enabled: bool = False
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

    @field_validator("bounds")
    @classmethod
    def _bounds_in_unit_square(
        cls, v: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        x_min, y_min, x_max, y_max = v
        for name, val in (("x_min", x_min), ("y_min", y_min), ("x_max", x_max), ("y_max", y_max)):
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"bounds.{name}={val} phải trong [0.0, 1.0]")
        if x_min >= x_max or y_min >= y_max:
            raise ValueError("bounds phải có x_min < x_max và y_min < y_max")
        return v


class TrackingSection(BaseModel):
    track_activation_threshold: float = Field(0.25, ge=0.0, le=1.0)
    lost_track_buffer: int = Field(30, ge=0)
    minimum_matching_threshold: float = Field(0.8, ge=0.0, le=1.0)
    minimum_consecutive_frames: int = Field(3, ge=1)


class SpeedSection(BaseModel):
    min_frames: int = Field(5, ge=1)


class AnalysisSection(BaseModel):
    default_interval_seconds: float = Field(30.0, gt=0)
    frame_skip: int = Field(1, ge=1, le=10)


class QueueSection(BaseModel):
    stopped_speed_kmh: float = Field(5.0, gt=0)
    window_frames: int = Field(5, ge=2)


class VehiclePCESection(BaseModel):
    car: float = Field(1.0, gt=0)
    motorcycle: float = Field(0.3, gt=0)
    bus: float = Field(3.0, gt=0)
    truck: float = Field(2.5, gt=0)


class InferenceConfigDTO(BaseModel):
    model: ModelSection
    detection: DetectionSection
    detection_roi: DetectionROISection = Field(default_factory=DetectionROISection)
    tracking: TrackingSection
    speed: SpeedSection
    analysis: AnalysisSection
    queue: QueueSection
    vehicle_pce: VehiclePCESection


# --- UI schema metadata (for InferenceSettingsPage form rendering) -----------


class FieldMeta(BaseModel):
    type: Literal["number", "integer", "boolean", "string", "string_list", "select"]
    label: str
    description: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    default: object | None = None
    ui_hint: str | None = None
    options: list[str] | None = None


class ModelFileInfo(BaseModel):
    name: str
    path: str
    size_mb: float
