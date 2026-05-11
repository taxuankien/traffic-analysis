from __future__ import annotations

from datetime import datetime

import pytest

from src.adapters.output.storage.json_repository import (
    JSONROIConfigRepository,
    JSONSessionRepository,
    JSONSourceRepository,
)
from src.domain.entities.analysis_session import AnalysisSession, SessionStatus
from src.domain.entities.roi_config import ROIConfig
from src.domain.entities.video_source import VideoSource
from src.domain.exceptions import (
    AnalysisSessionNotFoundError,
    ROIConfigNotFoundError,
    VideoSourceNotFoundError,
)
from src.domain.value_objects import CountingLine, LineDirection, ROIPolygon


def test_source_repository_crud(tmp_path):
    repo = JSONSourceRepository(tmp_path)
    src = VideoSource(id="cam_001", name="Cam 1", path=str(tmp_path / "a.mp4"))
    repo.save(src)

    assert [s.id for s in repo.list_all()] == ["cam_001"]
    fetched = repo.get("cam_001")
    assert fetched.name == "Cam 1"

    src.name = "Renamed"
    repo.save(src)
    assert repo.get("cam_001").name == "Renamed"

    repo.delete("cam_001")
    assert repo.list_all() == []
    with pytest.raises(VideoSourceNotFoundError):
        repo.get("cam_001")
    with pytest.raises(VideoSourceNotFoundError):
        repo.delete("cam_001")


def test_roi_config_repository(tmp_path):
    repo = JSONROIConfigRepository(tmp_path)
    cfg = ROIConfig(
        source_id="cam_001",
        roi_polygons=[ROIPolygon.from_points("lane_1", [(0, 0), (10, 0), (5, 10)])],
        counting_lines=[
            CountingLine("in", start=(0, 100), end=(200, 100), direction=LineDirection.IN)
        ],
        pixels_per_meter=12.5,
    )
    assert not repo.exists("cam_001")
    repo.save(cfg)
    assert repo.exists("cam_001")

    loaded = repo.load("cam_001")
    assert loaded.pixels_per_meter == 12.5
    assert loaded.roi_polygons[0].name == "lane_1"
    assert loaded.counting_lines[0].direction == LineDirection.IN

    with pytest.raises(ROIConfigNotFoundError):
        repo.load("missing")


def test_session_repository(tmp_path):
    repo = JSONSessionRepository(tmp_path)
    s1 = AnalysisSession(id="sess1", source_id="cam_001")
    s1.mark_completed()
    s2 = AnalysisSession(id="sess2", source_id="cam_001")
    repo.save(s1)
    repo.save(s2)

    sessions = repo.list_for_source("cam_001")
    assert {s.id for s in sessions} == {"sess1", "sess2"}
    assert repo.get("cam_001", "sess1").status == SessionStatus.COMPLETED

    with pytest.raises(AnalysisSessionNotFoundError):
        repo.get("cam_001", "missing")
