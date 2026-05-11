from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StartSessionRequest(BaseModel):
    interval_seconds: float = Field(30.0, gt=0)
    render_video: bool = False


class SessionProgress(BaseModel):
    processed_frames: int
    total_frames: int
    current_interval: int


class AnalysisSessionResponse(BaseModel):
    id: str
    source_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    interval_seconds: float
    progress: SessionProgress | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime


class IntervalResponse(BaseModel):
    timestamp: datetime
    duration_seconds: float
    vehicle_counts: dict[str, int]
    counts_in: dict[str, int] = Field(default_factory=dict)
    counts_out: dict[str, int] = Field(default_factory=dict)
    occupancy_ratio: float
    avg_speed_kmh: float
    queue_length: int
