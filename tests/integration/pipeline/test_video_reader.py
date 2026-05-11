from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.output.video.sv_video_reader import SVVideoReader

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "vehicles.mp4"
pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample video missing")


def test_metadata():
    reader = SVVideoReader()
    meta = reader.get_metadata(str(SAMPLE))
    assert meta.fps > 0
    assert meta.width > 0
    assert meta.height > 0


def test_get_frame_first():
    reader = SVVideoReader()
    frame = reader.get_frame(str(SAMPLE), 0)
    assert frame.ndim == 3
    assert frame.shape[2] == 3
