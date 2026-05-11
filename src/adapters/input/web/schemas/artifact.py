from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


ArtifactKind = Literal["csv", "video", "summary", "roi", "frame", "bundle"]


class ArtifactInfo(BaseModel):
    kind: ArtifactKind
    name: str
    size_bytes: int
    mtime: datetime
    download_url: str
    preview_url: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    source_id: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float
    interval_count: int
    interval_seconds: float
    totals: dict[str, int]
    avg_occupancy_ratio: float
    avg_speed_kmh: float
