from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class VideoMetadata:
    fps: float
    width: int
    height: int
    total_frames: int


class VideoReaderPort(ABC):
    @abstractmethod
    def get_metadata(self, source_path: str) -> VideoMetadata: ...

    @abstractmethod
    def get_frame(self, source_path: str, frame_index: int = 0) -> Any:
        """Return frame as numpy.ndarray (H, W, 3) BGR."""

    @abstractmethod
    def iter_frames(self, source_path: str) -> Iterator[Any]: ...
