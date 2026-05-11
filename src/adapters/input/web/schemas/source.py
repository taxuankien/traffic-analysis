from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class VideoSourceMetadata(BaseModel):
    fps: float | None = None
    total_frames: int | None = None
    width: int | None = None
    height: int | None = None


class VideoSourceResponse(BaseModel):
    id: str
    name: str
    path: str
    kind: Literal["file", "stream"] = "file"
    created_at: datetime
    metadata: VideoSourceMetadata | None = None
