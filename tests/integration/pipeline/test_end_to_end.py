"""End-to-end: add source -> seed ROI config -> run analysis -> read CSV via service."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.bootstrap.container import Container
from src.domain.entities.analysis_session import SessionStatus
from src.domain.entities.roi_config import ROIConfig
from src.domain.value_objects import CountingLine, LineDirection, ROIPolygon

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "data" / "vehicles.mp4"
WEIGHTS = ROOT / "models" / "yolov8n.pt"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample video missing")


def test_full_workflow(tmp_path):
    container = Container(data_dir=tmp_path, weights_path=str(WEIGHTS))
    dms = container.data_management_service()
    rois = container.roi_config_service()

    src = dms.add_source("Sample", str(SAMPLE))
    meta = container.video_reader.get_metadata(src.path)
    cfg = ROIConfig(
        source_id=src.id,
        roi_polygons=[
            ROIPolygon.from_points(
                "z1",
                [
                    (0, meta.height // 4),
                    (meta.width, meta.height // 4),
                    (meta.width, meta.height * 3 // 4),
                    (0, meta.height * 3 // 4),
                ],
            )
        ],
        counting_lines=[
            CountingLine(
                "l1",
                start=(0, meta.height // 2),
                end=(meta.width, meta.height // 2),
                direction=LineDirection.BOTH,
            )
        ],
        pixels_per_meter=10.0,
    )
    rois.save_config(cfg)

    analysis = container.analysis_service(frame_rate=int(meta.fps) or 30)
    session = analysis.start_session(src.id, interval_seconds=2.0)
    completed = analysis.run_session(session.id)
    assert completed.status == SessionStatus.COMPLETED

    intervals = dms.query_intervals(src.id, session_id=session.id)
    assert len(intervals) >= 1
    sessions = dms.list_sessions(src.id)
    assert any(s.id == session.id and s.status == SessionStatus.COMPLETED for s in sessions)
