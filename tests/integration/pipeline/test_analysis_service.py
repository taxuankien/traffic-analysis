from __future__ import annotations

from pathlib import Path

import pytest

from src.application.ports.input.analysis_port import AnalysisProgress
from src.bootstrap.container import Container
from src.domain.entities.analysis_session import SessionStatus
from src.domain.entities.roi_config import ROIConfig
from src.domain.value_objects import CountingLine, LineDirection, ROIPolygon

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "data" / "vehicles.mp4"
WEIGHTS = ROOT / "models" / "yolov8n.pt"

pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample video missing")


def _seed_config(container: Container, source_id: str, width: int, height: int) -> None:
    poly = ROIPolygon.from_points(
        "lane_1",
        [(0, height // 4), (width, height // 4), (width, height * 3 // 4), (0, height * 3 // 4)],
    )
    line = CountingLine(
        "line_in",
        start=(0, height // 2),
        end=(width, height // 2),
        direction=LineDirection.BOTH,
    )
    cfg = ROIConfig(
        source_id=source_id,
        roi_polygons=[poly],
        counting_lines=[line],
        pixels_per_meter=10.0,
    )
    container.roi_repo.save(cfg)


def test_run_session_writes_csv(tmp_path):
    container = Container(data_dir=tmp_path, weights_path=str(WEIGHTS))
    dms = container.data_management_service()
    src = dms.add_source("Sample", str(SAMPLE))

    meta = container.video_reader.get_metadata(src.path)
    _seed_config(container, src.id, meta.width, meta.height)

    analysis = container.analysis_service(frame_rate=int(meta.fps) or 30)
    session = analysis.start_session(src.id, interval_seconds=2.0)

    progress_seen = []
    completed = analysis.run_session(
        session.id, progress_cb=lambda p: progress_seen.append(p)
    )
    assert completed.status == SessionStatus.COMPLETED

    intervals = container.interval_repo.list(src.id, session.id)
    assert len(intervals) >= 1
    # CSV file exists at expected path
    csv_path = Path(container.interval_repo.csv_path(src.id, session.id))
    assert csv_path.exists()
