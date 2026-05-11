from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ROIPolygonDTO(BaseModel):
    name: str
    points: list[tuple[int, int]] = Field(min_length=3)


class CountingLineDTO(BaseModel):
    name: str
    start: tuple[int, int]
    end: tuple[int, int]
    direction: Literal["in", "out", "both"] = "both"


class ROIConfigDTO(BaseModel):
    source_id: str | None = None  # filled by router from path param
    reference_frame_index: int = 0
    roi_polygons: list[ROIPolygonDTO] = Field(default_factory=list)
    counting_lines: list[CountingLineDTO] = Field(default_factory=list)
    pixels_per_meter: float = 0.0
    detection_roi: tuple[float, float, float, float] | None = None
    created_at: datetime | None = None

    @field_validator("pixels_per_meter")
    @classmethod
    def _ppm_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("pixels_per_meter phải >= 0")
        return float(v)
