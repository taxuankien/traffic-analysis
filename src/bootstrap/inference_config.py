"""Inference & tracking configuration loaded from YAML.

Provides typed dataclasses for the parameters that affect prediction quality
(detection thresholds, tracking thresholds, image size, PCE values, ...). The
defaults defined here MUST stay in sync with ``config/inference.yaml`` so the
program behaves identically whether the YAML is present or absent.

Loader resolution order (when ``path`` is None):
    1. ``$TRAFFIC_INFERENCE_CONFIG`` environment variable
    2. ``<project_root>/config/inference.yaml``
    3. Fallback to dataclass defaults
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from src.bootstrap.paths import DEFAULT_CONFIG_DIR

logger = logging.getLogger(__name__)


_DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "inference.yaml"


def _err(field_name: str, value: Any, expected: str) -> str:
    return (
        f"Cấu hình '{field_name}' không hợp lệ: nhận được {value!r}, "
        f"yêu cầu {expected}."
    )


@dataclass
class ModelConfig:
    weights: str = "models/yolo11x.pt"
    device: str | None = None
    imgsz: int = 640
    half: bool = False
    max_det: int = 300
    agnostic_nms: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.weights, str) or not self.weights.strip():
            raise ValueError(_err("model.weights", self.weights, "đường dẫn file .pt"))
        if self.device is not None and not isinstance(self.device, str):
            raise ValueError(_err("model.device", self.device, "null hoặc chuỗi (vd 'cpu', 'cuda:0')"))
        if not isinstance(self.imgsz, int) or self.imgsz < 32 or self.imgsz % 32 != 0:
            raise ValueError(_err("model.imgsz", self.imgsz, "số nguyên ≥ 32 và là bội số của 32 (vd 640, 1280)"))
        if not isinstance(self.half, bool):
            raise ValueError(_err("model.half", self.half, "true hoặc false"))
        if not isinstance(self.max_det, int) or self.max_det <= 0:
            raise ValueError(_err("model.max_det", self.max_det, "số nguyên dương"))
        if not isinstance(self.agnostic_nms, bool):
            raise ValueError(_err("model.agnostic_nms", self.agnostic_nms, "true hoặc false"))


@dataclass
class DetectionConfig:
    confidence: float = 0.25
    iou: float = 0.7
    class_ids: list[int] = field(default_factory=lambda: [2, 3, 5, 7])

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError(_err("detection.confidence", self.confidence, "số thực trong [0.0, 1.0]"))
        if not 0.0 <= float(self.iou) <= 1.0:
            raise ValueError(_err("detection.iou", self.iou, "số thực trong [0.0, 1.0]"))
        if not isinstance(self.class_ids, list) or not all(
            isinstance(c, int) and c >= 0 for c in self.class_ids
        ):
            raise ValueError(
                _err("detection.class_ids", self.class_ids, "danh sách số nguyên không âm (COCO class IDs)")
            )


@dataclass
class DetectionROIConfig:
    """Rectangular crop applied to the frame BEFORE detection to cut inference cost.

    Bounds are normalized to ``[0.0, 1.0]`` in ``[x_min, y_min, x_max, y_max]`` order
    so the same config works across resolutions. Bbox coordinates returned by the
    detector are translated back into the original frame, so downstream zones,
    counting lines, and per-source polygon ROIs stay in original-frame space.
    """

    enabled: bool = False
    bounds: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0, 1.0])

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError(_err("detection_roi.enabled", self.enabled, "true hoặc false"))
        if not isinstance(self.bounds, list) or len(self.bounds) != 4:
            raise ValueError(
                _err(
                    "detection_roi.bounds",
                    self.bounds,
                    "danh sách 4 số thực [x_min, y_min, x_max, y_max] đã chuẩn hóa về [0.0, 1.0]",
                )
            )
        try:
            x_min, y_min, x_max, y_max = (float(v) for v in self.bounds)
        except (TypeError, ValueError):
            raise ValueError(
                _err("detection_roi.bounds", self.bounds, "4 số thực trong [0.0, 1.0]")
            )
        for name, value in (("x_min", x_min), ("y_min", y_min), ("x_max", x_max), ("y_max", y_max)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    _err(f"detection_roi.bounds.{name}", value, "số thực trong [0.0, 1.0]")
                )
        if x_min >= x_max or y_min >= y_max:
            raise ValueError(
                _err(
                    "detection_roi.bounds",
                    self.bounds,
                    "x_min < x_max và y_min < y_max (vùng có diện tích > 0)",
                )
            )
        self.bounds = [x_min, y_min, x_max, y_max]

    def is_full_frame(self) -> bool:
        x_min, y_min, x_max, y_max = self.bounds
        return x_min == 0.0 and y_min == 0.0 and x_max == 1.0 and y_max == 1.0


@dataclass
class TrackingConfig:
    track_activation_threshold: float = 0.25
    lost_track_buffer: int = 30
    minimum_matching_threshold: float = 0.8
    minimum_consecutive_frames: int = 3

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.track_activation_threshold) <= 1.0:
            raise ValueError(
                _err("tracking.track_activation_threshold", self.track_activation_threshold, "số thực trong [0.0, 1.0]")
            )
        if not isinstance(self.lost_track_buffer, int) or self.lost_track_buffer < 0:
            raise ValueError(
                _err("tracking.lost_track_buffer", self.lost_track_buffer, "số nguyên không âm")
            )
        if not 0.0 <= float(self.minimum_matching_threshold) <= 1.0:
            raise ValueError(
                _err("tracking.minimum_matching_threshold", self.minimum_matching_threshold, "số thực trong [0.0, 1.0]")
            )
        if not isinstance(self.minimum_consecutive_frames, int) or self.minimum_consecutive_frames < 1:
            raise ValueError(
                _err("tracking.minimum_consecutive_frames", self.minimum_consecutive_frames, "số nguyên ≥ 1")
            )


@dataclass
class SpeedConfig:
    min_frames: int = 5

    def __post_init__(self) -> None:
        if not isinstance(self.min_frames, int) or self.min_frames < 1:
            raise ValueError(_err("speed.min_frames", self.min_frames, "số nguyên ≥ 1"))


@dataclass
class AnalysisConfig:
    default_interval_seconds: float = 30.0
    frame_skip: int = 1

    def __post_init__(self) -> None:
        if float(self.default_interval_seconds) <= 0:
            raise ValueError(
                _err("analysis.default_interval_seconds", self.default_interval_seconds, "số thực dương")
            )
        if not isinstance(self.frame_skip, int) or self.frame_skip < 1:
            raise ValueError(
                _err(
                    "analysis.frame_skip",
                    self.frame_skip,
                    "số nguyên ≥ 1 (1 = không skip; N = chỉ xử lý 1/N frame)",
                )
            )


@dataclass
class QueueConfig:
    stopped_speed_kmh: float = 5.0
    window_frames: int = 5

    def __post_init__(self) -> None:
        if float(self.stopped_speed_kmh) <= 0:
            raise ValueError(
                _err("queue.stopped_speed_kmh", self.stopped_speed_kmh, "số thực dương (km/h)")
            )
        if not isinstance(self.window_frames, int) or self.window_frames < 2:
            raise ValueError(_err("queue.window_frames", self.window_frames, "số nguyên ≥ 2"))


@dataclass
class VehiclePCEConfig:
    car: float = 1.0
    motorcycle: float = 0.3  # TCVN 4054 — sát giao thông VN hơn chuẩn US (0.5)
    bus: float = 3.0
    truck: float = 2.5

    def __post_init__(self) -> None:
        for name in ("car", "motorcycle", "bus", "truck"):
            v = getattr(self, name)
            if float(v) <= 0:
                raise ValueError(_err(f"vehicle_pce.{name}", v, "số thực dương"))

    def as_mapping(self) -> dict[str, float]:
        return {
            "car": float(self.car),
            "motorcycle": float(self.motorcycle),
            "bus": float(self.bus),
            "truck": float(self.truck),
        }


_SECTION_TYPES: dict[str, type] = {
    "model": ModelConfig,
    "detection": DetectionConfig,
    "detection_roi": DetectionROIConfig,
    "tracking": TrackingConfig,
    "speed": SpeedConfig,
    "analysis": AnalysisConfig,
    "queue": QueueConfig,
    "vehicle_pce": VehiclePCEConfig,
}


@dataclass
class InferenceConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    detection_roi: DetectionROIConfig = field(default_factory=DetectionROIConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    speed: SpeedConfig = field(default_factory=SpeedConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    queue: QueueConfig = field(default_factory=QueueConfig)
    vehicle_pce: VehiclePCEConfig = field(default_factory=VehiclePCEConfig)
    source_path: Path | None = None  # set by load() so callers can log provenance

    @classmethod
    def load(cls, path: str | Path | None = None) -> "InferenceConfig":
        resolved = cls._resolve_path(path)
        if resolved is None or not resolved.is_file():
            if path is not None:
                raise FileNotFoundError(
                    f"Không tìm thấy file cấu hình tại {Path(path).resolve()}"
                )
            logger.info(
                "Không tìm thấy file cấu hình inference, dùng giá trị mặc định trong code."
            )
            return cls()

        try:
            import yaml  # transitive dep via ultralytics; explicit in requirements.txt
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Cần cài 'pyyaml' để load file cấu hình YAML. Chạy: pip install pyyaml"
            ) from exc

        with resolved.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if not isinstance(raw, dict):
            raise ValueError(
                f"File cấu hình {resolved} phải là object YAML cấp cao nhất (key: value)."
            )

        cfg = cls._from_mapping(raw)
        cfg.source_path = resolved
        logger.info("Đã load cấu hình inference từ %s", resolved)
        return cfg

    @classmethod
    def _resolve_path(cls, path: str | Path | None) -> Path | None:
        if path is not None:
            return Path(path)
        env = os.environ.get("TRAFFIC_INFERENCE_CONFIG")
        if env:
            return Path(env)
        if _DEFAULT_CONFIG_PATH.is_file():
            return _DEFAULT_CONFIG_PATH
        return None

    @classmethod
    def _from_mapping(cls, raw: dict[str, Any]) -> "InferenceConfig":
        unknown = set(raw.keys()) - set(_SECTION_TYPES.keys())
        if unknown:
            valid = ", ".join(sorted(_SECTION_TYPES.keys()))
            raise ValueError(
                f"File cấu hình chứa section không hợp lệ: {sorted(unknown)}. "
                f"Các section hợp lệ: {valid}."
            )

        sections: dict[str, Any] = {}
        for name, type_ in _SECTION_TYPES.items():
            section_raw = raw.get(name)
            if section_raw is None:
                sections[name] = type_()  # all defaults
                continue
            if not isinstance(section_raw, dict):
                raise ValueError(
                    f"Section '{name}' phải là object YAML, nhận được {type(section_raw).__name__}."
                )
            valid_keys = {f.name for f in fields(type_)}
            unknown_keys = set(section_raw.keys()) - valid_keys
            if unknown_keys:
                valid = ", ".join(sorted(valid_keys))
                raise ValueError(
                    f"Section '{name}' chứa key không hợp lệ: {sorted(unknown_keys)}. "
                    f"Các key hợp lệ: {valid}."
                )
            sections[name] = type_(**section_raw)

        return cls(**sections)
