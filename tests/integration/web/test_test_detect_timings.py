"""Test inference timings trong response của ``POST /api/sources/{id}/test-detect``.

Dùng fake detector + monkeypatch ``Container.frame_extraction_service`` để cô lập
khỏi YOLO/video reader thật.
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np
import pytest

from src.application.ports.input.frame_extraction_port import TestDetectionResult
from src.application.services.frame_extraction_service import FrameExtractionService
from src.domain.entities.video_source import VideoSource, VideoSourceKind


class _FakeFrameExtractionService:
    """Mimics FrameExtractionService.run_test_detection with realistic timings."""

    def run_test_detection(self, source_id, frame_index, detection_roi=None):
        time.sleep(0.01)  # simulate inference
        annotated = np.zeros((480, 640, 3), dtype=np.uint8)
        return TestDetectionResult(
            frame_index=frame_index,
            annotated_frame=annotated,
            detections=[
                {"class_id": 2, "class_name": "car", "confidence": 0.9, "bbox_xyxy": [0, 0, 100, 100]}
            ],
            counts_by_class={"car": 1},
            inference_ms=12.5,
            annotation_ms=1.2,
            total_ms=15.0,
            device="cuda:0",
            image_size=(640, 480),
        )


@pytest.fixture
def client_with_fake_extraction(client, container, monkeypatch):
    # Seed a source.
    source = VideoSource(id="src_t", name="Test", path="/tmp/fake.mp4", kind=VideoSourceKind.FILE)
    container.source_repo.save(source)

    fake = _FakeFrameExtractionService()
    monkeypatch.setattr(container, "frame_extraction_service", lambda: fake)
    return client


def test_test_detect_returns_timings(client_with_fake_extraction):
    r = client_with_fake_extraction.post(
        "/api/sources/src_t/test-detect", json={"frame": 0, "annotate": False}
    )
    assert r.status_code == 200
    body = r.json()
    assert "timings" in body
    t = body["timings"]
    assert t["inference_ms"] == 12.5
    assert t["annotation_ms"] == 1.2
    assert t["total_ms"] == 15.0
    assert t["device"] == "cuda:0"
    assert t["image_size"] == [640, 480]
    # fps_estimate = 1000 / 12.5 = 80.0
    assert t["fps_estimate"] == 80.0


def test_test_detect_fps_estimate_handles_zero_inference(client, container, monkeypatch):
    source = VideoSource(id="src_z", name="Z", path="/tmp/z.mp4", kind=VideoSourceKind.FILE)
    container.source_repo.save(source)

    class _NoTimingFake:
        def run_test_detection(self, *_a, **_k):
            return TestDetectionResult(
                frame_index=0,
                annotated_frame=np.zeros((10, 10, 3), dtype=np.uint8),
                detections=[],
                counts_by_class={},
                inference_ms=None,
                annotation_ms=None,
                total_ms=None,
            )

    monkeypatch.setattr(container, "frame_extraction_service", lambda: _NoTimingFake())
    r = client.post("/api/sources/src_z/test-detect", json={"frame": 0, "annotate": False})
    assert r.status_code == 200
    t = r.json()["timings"]
    assert t["inference_ms"] is None
    assert t["fps_estimate"] is None
