from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FrameDetectionView:
    """A single annotated frame plus a structured list of detections for inspection."""

    frame_index: int
    frame: Any  # np.ndarray, annotated
    detections: list[dict] = field(default_factory=list)


@dataclass
class RenderProgress:
    current_frame: int
    total_frames: int


RenderProgressCallback = Callable[[RenderProgress], None]


class VisualizationPort(ABC):
    @abstractmethod
    def preview_slice(
        self,
        source_id: str,
        start_frame: int,
        end_frame: int,
    ) -> list[FrameDetectionView]:
        """Run detection on the [start_frame, end_frame) slice and return annotated frames."""

    @abstractmethod
    def render_full_video(
        self,
        source_id: str,
        target_path: str,
        progress_cb: RenderProgressCallback | None = None,
    ) -> str:
        """Run detection + tracking on the whole video and write an annotated mp4 to ``target_path``.

        Annotation includes bbox, labels, tracks, counting lines, ROI polygons, and live counter text.
        """
