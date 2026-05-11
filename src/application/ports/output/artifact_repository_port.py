"""Output port cho việc enumerate / locate artifacts của 1 session.

Web layer dùng để:
    - ``GET /api/sessions/{id}/artifacts`` → list metadata
    - ``GET /api/sessions/{id}/download/<kind>`` → trả file qua FileResponse/Stream
    - ``GET /api/sessions/{id}/download/bundle.zip`` → enumerate rồi zip
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

ArtifactKind = Literal["csv", "video", "summary", "roi", "frame"]


@dataclass(frozen=True)
class Artifact:
    kind: ArtifactKind
    name: str
    path: Path
    size_bytes: int
    mtime: datetime


class ArtifactRepositoryPort(ABC):
    @abstractmethod
    def list_for_session(self, source_id: str, session_id: str) -> list[Artifact]:
        """Enumerate artifacts đã có cho 1 session. ROI artifact là per-source nên
        repo nội suy ra path của ROI config theo ``source_id``.
        """

    @abstractmethod
    def get(
        self, source_id: str, session_id: str, kind: ArtifactKind
    ) -> Artifact | None:
        """Trả Artifact đơn lẻ; ``None`` nếu file không tồn tại."""

    @abstractmethod
    def get_roi(self, source_id: str) -> Artifact | None:
        """ROI config artifact (per-source, không phụ thuộc session)."""
