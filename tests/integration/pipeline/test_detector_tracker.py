from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "data" / "vehicles.mp4"
WEIGHTS_DIR = ROOT / "models"
WEIGHTS_DIR.mkdir(exist_ok=True)
WEIGHTS = WEIGHTS_DIR / "yolov8n.pt"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample video missing")


def test_yolo_detector_filters_to_vehicles():
    from src.adapters.output.detection.yolo_detector import YOLODetector
    from src.adapters.output.video.sv_video_reader import SVVideoReader
    from src.domain.value_objects.vehicle_type import VEHICLE_CLASS_IDS

    detector = YOLODetector(weights=str(WEIGHTS))
    reader = SVVideoReader()
    frame = reader.get_frame(str(SAMPLE), 0)
    det = detector.detect(frame).raw
    if det.class_id is not None and len(det) > 0:
        assert set(np.unique(det.class_id).tolist()).issubset(VEHICLE_CLASS_IDS)


def test_bytetrack_assigns_ids_across_frames():
    from src.adapters.output.detection.bytetrack_tracker import SVByteTracker
    from src.adapters.output.detection.yolo_detector import YOLODetector
    from src.adapters.output.video.sv_video_reader import SVVideoReader

    detector = YOLODetector(weights=str(WEIGHTS))
    tracker = SVByteTracker(frame_rate=30)
    reader = SVVideoReader()

    seen_ids: set[int] = set()
    for idx, frame in enumerate(reader.iter_frames(str(SAMPLE))):
        if idx >= 30:
            break
        det = detector.detect(frame)
        det = tracker.update(det)
        if det.raw.tracker_id is not None:
            seen_ids.update(int(t) for t in det.raw.tracker_id if t is not None)
    assert len(seen_ids) >= 1
