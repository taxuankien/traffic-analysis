from __future__ import annotations

import supervision as sv

from src.application.ports.output.detector_port import Detection
from src.application.ports.output.tracker_port import TrackerPort


class SVByteTracker(TrackerPort):
    def __init__(
        self,
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 30,
        minimum_matching_threshold: float = 0.8,
        frame_rate: int = 30,
        minimum_consecutive_frames: int = 3,
    ) -> None:
        self._kwargs = dict(
            track_activation_threshold=track_activation_threshold,
            lost_track_buffer=lost_track_buffer,
            minimum_matching_threshold=minimum_matching_threshold,
            frame_rate=frame_rate,
            minimum_consecutive_frames=minimum_consecutive_frames,
        )
        self._tracker = sv.ByteTrack(**self._kwargs)

    def update(self, detection: Detection) -> Detection:
        updated = self._tracker.update_with_detections(detection.raw)
        return Detection(raw=updated)

    def reset(self) -> None:
        self._tracker = sv.ByteTrack(**self._kwargs)
