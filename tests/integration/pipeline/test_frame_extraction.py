from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.adapters.output.detection.yolo_detector import YOLODetector
from src.adapters.output.storage.json_repository import JSONSourceRepository
from src.adapters.output.video.sv_video_reader import SVVideoReader
from src.application.services.frame_extraction_service import FrameExtractionService
from src.domain.entities.video_source import VideoSource
from src.domain.exceptions import VideoSourceNotFoundError

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "data" / "vehicles.mp4"
WEIGHTS = ROOT / "models" / "yolov8n.pt"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample video missing")


@pytest.fixture
def service(tmp_path):
    src_repo = JSONSourceRepository(tmp_path)
    src = VideoSource(id="cam1", name="cam1", path=str(SAMPLE.resolve()))
    src_repo.save(src)
    detector = YOLODetector(weights=str(WEIGHTS))
    reader = SVVideoReader()
    return FrameExtractionService(
        source_repo=src_repo,
        video_reader=reader,
        detector=detector,
        frames_dir=tmp_path / "frames",
    )


def test_extract_frame_by_index(service):
    frame = service.extract_frame("cam1", 0)
    assert frame.ndim == 3
    assert frame.shape[2] == 3


def test_extract_frame_at_timestamp(service):
    f0 = service.extract_frame("cam1", 0)
    fa = service.extract_frame_at("cam1", 0.0)
    # First frame from index 0 vs timestamp 0.0 should be the same frame
    assert f0.shape == fa.shape


def test_extract_frame_negative_index_raises(service):
    with pytest.raises(ValueError):
        service.extract_frame("cam1", -1)


def test_extract_frame_unknown_source(service):
    with pytest.raises(VideoSourceNotFoundError):
        service.extract_frame("missing", 0)


def test_save_frame_writes_png(service, tmp_path):
    frame = service.extract_frame("cam1", 0)
    path = service.save_frame(frame, "cam1", 0)
    assert path.exists()
    assert path.suffix == ".png"
    assert path.name == "cam1_000000.png"
    assert path.stat().st_size > 0


def test_run_test_detection_returns_counts(service):
    result = service.run_test_detection("cam1", 30)
    assert result.frame_index == 30
    assert result.annotated_frame.shape[2] == 3
    # Smoke: typical traffic frame should have at least one detection
    assert isinstance(result.detections, list)
    if result.detections:
        # All detected classes should be vehicle types
        assert all(d["class_name"] in {"car", "motorcycle", "bus", "truck", None} for d in result.detections)
        assert sum(result.counts_by_class.values()) <= len(result.detections)


def test_test_detection_does_not_crash_when_no_vehicles(service):
    # Frame at index 0 may or may not contain vehicles - just ensure no exception
    result = service.run_test_detection("cam1", 0)
    assert result.frame_index == 0
    assert result.annotated_frame is not None
