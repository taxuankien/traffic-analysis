from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.exceptions import CalibrationError, InvalidROIConfigError
from src.domain.value_objects.counting_line import CountingLine
from src.domain.value_objects.roi_polygon import ROIPolygon


@dataclass
class ROIConfig:
    source_id: str
    reference_frame_index: int = 0
    roi_polygons: list[ROIPolygon] = field(default_factory=list)
    counting_lines: list[CountingLine] = field(default_factory=list)
    pixels_per_meter: float = 0.0
    # Normalized [x_min, y_min, x_max, y_max] in [0.0, 1.0]; None → fall back to YAML default.
    detection_roi: tuple[float, float, float, float] | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if self.reference_frame_index < 0:
            raise InvalidROIConfigError("reference_frame_index must be >= 0")
        if self.pixels_per_meter < 0:
            raise CalibrationError("pixels_per_meter must be >= 0")
        if self.detection_roi is not None:
            self.detection_roi = self._validate_detection_roi(self.detection_roi)

    @staticmethod
    def _validate_detection_roi(value) -> tuple[float, float, float, float]:
        try:
            bounds = tuple(float(v) for v in value)
        except (TypeError, ValueError) as e:
            raise InvalidROIConfigError(
                f"detection_roi must be 4 numbers in [0.0, 1.0], got {value!r}"
            ) from e
        if len(bounds) != 4:
            raise InvalidROIConfigError(
                f"detection_roi must have 4 elements [x_min, y_min, x_max, y_max], got {len(bounds)}"
            )
        x_min, y_min, x_max, y_max = bounds
        for name, v in (("x_min", x_min), ("y_min", y_min), ("x_max", x_max), ("y_max", y_max)):
            if not 0.0 <= v <= 1.0:
                raise InvalidROIConfigError(
                    f"detection_roi.{name}={v} outside [0.0, 1.0]"
                )
        if x_min >= x_max or y_min >= y_max:
            raise InvalidROIConfigError(
                f"detection_roi must satisfy x_min<x_max and y_min<y_max, got {bounds}"
            )
        return bounds

    def has_calibration(self) -> bool:
        return self.pixels_per_meter > 0

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "reference_frame_index": self.reference_frame_index,
            "roi_polygons": [p.to_dict() for p in self.roi_polygons],
            "counting_lines": [l.to_dict() for l in self.counting_lines],
            "pixels_per_meter": self.pixels_per_meter,
            "detection_roi": list(self.detection_roi) if self.detection_roi is not None else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ROIConfig":
        created_at = data.get("created_at")
        det_roi = data.get("detection_roi")
        return cls(
            source_id=data["source_id"],
            reference_frame_index=int(data.get("reference_frame_index", 0)),
            roi_polygons=[ROIPolygon.from_dict(p) for p in data.get("roi_polygons", [])],
            counting_lines=[CountingLine.from_dict(l) for l in data.get("counting_lines", [])],
            pixels_per_meter=float(data.get("pixels_per_meter", 0.0)),
            detection_roi=tuple(det_roi) if det_roi is not None else None,
            created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(),
        )
