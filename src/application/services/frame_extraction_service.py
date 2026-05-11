"""Frame-extraction + one-shot test-detection service (Luồng 1b).

Stateless — does not touch sessions or aggregate intervals. The detector is reused
between calls; we never call the tracker because each call is a single frame.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.adapters.output.video.frame_annotator import FrameAnnotator
from src.application.ports.input.frame_extraction_port import (
    FrameExtractionPort,
    TestDetectionResult,
)
from src.application.ports.output.detector_port import DetectorPort
from src.application.ports.output.repository_port import SourceRepositoryPort
from src.application.ports.output.video_reader_port import VideoReaderPort
from src.domain.value_objects.vehicle_type import COCO_TO_VEHICLE_TYPE


class FrameExtractionService(FrameExtractionPort):
    def __init__(
        self,
        source_repo: SourceRepositoryPort,
        video_reader: VideoReaderPort,
        detector: DetectorPort,
        frames_dir: str | Path,
    ) -> None:
        self._sources = source_repo
        self._video = video_reader
        self._detector = detector
        self._frames_dir = Path(frames_dir)
        self._annotator: FrameAnnotator | None = None

    # --- Extraction ----------------------------------------------------------

    def extract_frame(self, source_id: str, frame_index: int) -> np.ndarray:
        if frame_index < 0:
            raise ValueError("frame_index must be >= 0")
        source = self._sources.get(source_id)
        return self._video.get_frame(source.path, frame_index)

    def extract_frame_at(self, source_id: str, timestamp_sec: float) -> np.ndarray:
        if timestamp_sec < 0:
            raise ValueError("timestamp_sec must be >= 0")
        source = self._sources.get(source_id)
        meta = self._video.get_metadata(source.path)
        if meta.fps <= 0:
            raise ValueError(f"Video {source_id} has invalid fps={meta.fps}")
        idx = int(round(timestamp_sec * meta.fps))
        if meta.total_frames > 0:
            idx = min(idx, meta.total_frames - 1)
        return self._video.get_frame(source.path, idx)

    # --- Save ----------------------------------------------------------------

    def save_frame(self, frame: np.ndarray, source_id: str, frame_index: int) -> Path:
        self._frames_dir.mkdir(parents=True, exist_ok=True)
        path = self._frames_dir / f"{source_id}_{frame_index:06d}.png"
        ok = cv2.imwrite(str(path), frame)
        if not ok:
            raise IOError(f"Failed to write PNG at {path}")
        return path

    # --- Test detection ------------------------------------------------------

    def run_test_detection(
        self,
        source_id: str,
        frame_index: int,
        detection_roi: tuple[float, float, float, float] | None = None,
    ) -> TestDetectionResult:
        t_start = time.perf_counter()
        frame = self.extract_frame(source_id, frame_index)
        applied_roi = detection_roi is not None and hasattr(self._detector, "set_roi_bounds")
        if applied_roi:
            self._detector.set_roi_bounds(detection_roi)
        try:
            t_inf = time.perf_counter()
            detection = self._detector.detect(frame)
            inference_ms = (time.perf_counter() - t_inf) * 1000.0
        finally:
            if applied_roi:
                self._detector.set_roi_bounds(None)
        raw = detection.raw

        annotator = self._get_annotator()
        t_annot = time.perf_counter()
        annotated = annotator.annotate(frame, raw)
        annotation_ms = (time.perf_counter() - t_annot) * 1000.0

        items: list[dict] = []
        counts: dict[str, int] = {}
        if raw is not None and len(raw) > 0:
            for i in range(len(raw)):
                cid = int(raw.class_id[i]) if raw.class_id is not None else None
                conf = float(raw.confidence[i]) if raw.confidence is not None else None
                vt = COCO_TO_VEHICLE_TYPE.get(cid) if cid is not None else None
                cls_name = vt.name if vt is not None else None
                if cls_name:
                    counts[cls_name] = counts.get(cls_name, 0) + 1
                items.append({
                    "class_id": cid,
                    "class_name": cls_name,
                    "confidence": conf,
                    "bbox_xyxy": [float(v) for v in raw.xyxy[i]],
                })

        height, width = frame.shape[:2] if hasattr(frame, "shape") else (None, None)
        return TestDetectionResult(
            frame_index=frame_index,
            annotated_frame=annotated,
            detections=items,
            counts_by_class=counts,
            inference_ms=round(inference_ms, 2),
            annotation_ms=round(annotation_ms, 2),
            total_ms=round((time.perf_counter() - t_start) * 1000.0, 2),
            device=self._get_detector_device(),
            image_size=(int(width), int(height)) if width and height else None,
        )

    def _get_detector_device(self) -> str | None:
        """Best-effort: tìm device thật detector đang chạy.

        Ưu tiên attribute ``_device`` set ở init; nếu None (auto), peek vào
        ultralytics model nếu khả dụng. Trả ``None`` khi không lấy được —
        UI sẽ hiển thị 'auto' thay vì sai lệch.
        """
        explicit = getattr(self._detector, "_device", None)
        if explicit:
            return explicit
        model = getattr(self._detector, "_model", None)
        try:
            device = getattr(model, "device", None)
            if device is not None:
                return str(device)
        except Exception:  # noqa: BLE001
            pass
        return None

    # --- Helpers -------------------------------------------------------------

    def _get_annotator(self) -> FrameAnnotator:
        if self._annotator is None:
            class_names = getattr(self._detector, "class_names", {}) or {}
            self._annotator = FrameAnnotator(class_names=class_names)
        return self._annotator
