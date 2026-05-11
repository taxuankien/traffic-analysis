from __future__ import annotations

from typing import Iterator

import cv2
import numpy as np
import supervision as sv

from src.application.ports.output.video_reader_port import (
    VideoMetadata,
    VideoReaderPort,
)


class SVVideoReader(VideoReaderPort):
    """Video reader backed by ``supervision`` + OpenCV."""

    def get_metadata(self, source_path: str) -> VideoMetadata:
        info = sv.VideoInfo.from_video_path(source_path)
        return VideoMetadata(
            fps=float(info.fps),
            width=int(info.width),
            height=int(info.height),
            total_frames=int(info.total_frames or 0),
        )

    def get_frame(self, source_path: str, frame_index: int = 0) -> np.ndarray:
        cap = cv2.VideoCapture(source_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {source_path}")
        try:
            if frame_index > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_index))
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError(
                    f"Failed to read frame {frame_index} from {source_path}"
                )
            return frame
        finally:
            cap.release()

    def iter_frames(self, source_path: str) -> Iterator[np.ndarray]:
        return sv.get_video_frames_generator(source_path=source_path)
