from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.adapters.output.storage.csv_repository import CSVIntervalRepository
from src.adapters.output.storage.json_repository import (
    JSONSessionRepository,
    JSONSourceRepository,
)
from src.application.services.data_management_service import DataManagementService
from src.domain.entities.analysis_session import AnalysisSession
from src.domain.value_objects import AnalysisInterval


@pytest.fixture
def service(tmp_path):
    return DataManagementService(
        source_repo=JSONSourceRepository(tmp_path),
        session_repo=JSONSessionRepository(tmp_path),
        interval_repo=CSVIntervalRepository(tmp_path),
    )


def test_add_list_delete_source(service: DataManagementService, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"\0")
    src = service.add_source("Cam 1", str(video_path))
    assert src.id.startswith("src_")

    listed = service.list_sources()
    assert len(listed) == 1
    fetched = service.get_source(src.id)
    assert fetched.path.endswith("video.mp4")

    service.delete_source(src.id)
    assert service.list_sources() == []


def test_query_intervals_by_time_range(service: DataManagementService, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\0")
    src = service.add_source("Cam", str(video))
    sess = AnalysisSession(id="sess1", source_id=src.id)
    sess.mark_completed()
    service._sessions.save(sess)

    base = datetime(2026, 4, 29, 9, 0, 0)
    for i in range(4):
        service._intervals.append(
            src.id,
            sess.id,
            AnalysisInterval(
                timestamp=base + timedelta(seconds=30 * i),
                duration_seconds=30.0,
                vehicle_counts={"car": i + 1},
            ),
        )
    out = service.query_intervals(
        src.id,
        session_id=sess.id,
        start=base + timedelta(seconds=29),
        end=base + timedelta(seconds=61),
    )
    assert [i.vehicle_counts["car"] for i in out] == [2, 3]


def test_query_intervals_all_sessions(service: DataManagementService, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\0")
    src = service.add_source("Cam", str(video))
    s1 = AnalysisSession(id="sess1", source_id=src.id)
    s2 = AnalysisSession(id="sess2", source_id=src.id)
    service._sessions.save(s1)
    service._sessions.save(s2)

    base = datetime(2026, 4, 29, 9, 0, 0)
    service._intervals.append(
        src.id, s1.id, AnalysisInterval(base, 30, vehicle_counts={"car": 1})
    )
    service._intervals.append(
        src.id,
        s2.id,
        AnalysisInterval(base + timedelta(seconds=30), 30, vehicle_counts={"car": 2}),
    )
    out = service.query_intervals(src.id)
    assert [i.vehicle_counts["car"] for i in out] == [1, 2]


def test_export_csv(service: DataManagementService, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\0")
    src = service.add_source("Cam", str(video))
    service._intervals.append(
        src.id,
        "sess1",
        AnalysisInterval(
            datetime.now(), 30.0, vehicle_counts={"car": 5}
        ),
    )
    target = tmp_path / "export.csv"
    out = service.export_csv(src.id, "sess1", str(target))
    assert target.exists()
    assert out == str(target)
