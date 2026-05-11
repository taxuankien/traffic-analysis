from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class VideoSourceKind(str, Enum):
    FILE = "file"
    STREAM = "stream"


@dataclass
class VideoSource:
    id: str
    name: str
    path: str
    kind: VideoSourceKind = VideoSourceKind.FILE
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    total_frames: int | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "kind": self.kind.value,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "total_frames": self.total_frames,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VideoSource":
        created_at = data.get("created_at")
        return cls(
            id=data["id"],
            name=data["name"],
            path=data["path"],
            kind=VideoSourceKind(data.get("kind", "file")),
            fps=data.get("fps"),
            width=data.get("width"),
            height=data.get("height"),
            total_frames=data.get("total_frames"),
            created_at=datetime.fromisoformat(created_at) if created_at else datetime.now(),
        )
