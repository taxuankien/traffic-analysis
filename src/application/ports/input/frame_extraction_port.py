"""Use case for the *test-frame* flow (Luồng 1b).

Lets the user pick a frame at any point in a video, optionally run a one-shot
detection on it for inspection, and save the result as PNG.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TestDetectionResult:
    """Output of a one-shot test detection on a single frame.

    Trường ``timings`` chứa số liệu hiệu năng để UI hiển thị, giúp người dùng
    đánh giá tốc độ đáp ứng của model trên phần cứng hiện tại trước khi chạy
    batch dài.
    """

    frame_index: int
    annotated_frame: Any  # np.ndarray (BGR), bbox/labels drawn on it
    detections: list[dict] = field(default_factory=list)
    counts_by_class: dict[str, int] = field(default_factory=dict)
    # Timings (ms) — None khi detector không cung cấp phép đo (legacy tests).
    inference_ms: float | None = None
    annotation_ms: float | None = None
    total_ms: float | None = None
    device: str | None = None      # device thực tế detector dùng (cpu / cuda:0 / mps)
    image_size: tuple[int, int] | None = None  # (width, height) frame


class FrameExtractionPort(ABC):
    @abstractmethod
    def extract_frame(self, source_id: str, frame_index: int) -> Any:
        """Return raw frame (np.ndarray, BGR) at ``frame_index``."""

    @abstractmethod
    def extract_frame_at(self, source_id: str, timestamp_sec: float) -> Any:
        """Return raw frame (np.ndarray, BGR) at ``timestamp_sec``.

        Internally rounds to the nearest frame index using video fps.
        """

    @abstractmethod
    def save_frame(self, frame: Any, source_id: str, frame_index: int) -> Path:
        """Persist ``frame`` as PNG under ``data/frames/<source_id>_<frame_index>.png``."""

    @abstractmethod
    def run_test_detection(
        self,
        source_id: str,
        frame_index: int,
        detection_roi: tuple[float, float, float, float] | None = None,
    ) -> TestDetectionResult:
        """Extract frame at ``frame_index``, run detection (no tracking), annotate.

        ``detection_roi`` is normalized ``(x_min, y_min, x_max, y_max)`` in ``[0.0, 1.0]``;
        when provided, the detector crops to that region for this call only (UI uses this
        to preview the effect of a draft Detection ROI before saving). ``None`` falls back
        to the construction-time default (typically the YAML config).

        This is *stateless* — it does not write to storage and does not affect any session.
        """
