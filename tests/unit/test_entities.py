from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.entities import (
    AnalysisResult,
    AnalysisSession,
    ROIConfig,
    SessionStatus,
    VehicleTrack,
    VideoSource,
    VideoSourceKind,
)
from src.domain.entities.vehicle_track import TrackPoint
from src.domain.exceptions import CalibrationError
from src.domain.value_objects import (
    AnalysisInterval,
    CountingLine,
    LineDirection,
    ROIPolygon,
    VehicleType,
)


class TestVideoSource:
    def test_round_trip(self):
        src = VideoSource(
            id="cam_001",
            name="Cam 1",
            path="data/vehicles.mp4",
            kind=VideoSourceKind.FILE,
            fps=30.0,
            width=1920,
            height=1080,
            total_frames=900,
        )
        restored = VideoSource.from_dict(src.to_dict())
        assert restored.id == src.id
        assert restored.kind == VideoSourceKind.FILE
        assert restored.fps == 30.0


class TestROIConfig:
    def test_calibration_negative_raises(self):
        with pytest.raises(CalibrationError):
            ROIConfig(source_id="s1", pixels_per_meter=-1.0)

    def test_round_trip(self):
        cfg = ROIConfig(
            source_id="cam_001",
            reference_frame_index=0,
            roi_polygons=[ROIPolygon.from_points("lane_1", [(0, 0), (10, 0), (5, 10)])],
            counting_lines=[
                CountingLine("in", start=(0, 100), end=(200, 100), direction=LineDirection.IN),
            ],
            pixels_per_meter=12.5,
        )
        restored = ROIConfig.from_dict(cfg.to_dict())
        assert restored.source_id == cfg.source_id
        assert restored.pixels_per_meter == 12.5
        assert restored.roi_polygons[0].name == "lane_1"
        assert restored.counting_lines[0].direction == LineDirection.IN

    def test_has_calibration(self):
        cfg = ROIConfig(source_id="s1")
        assert not cfg.has_calibration()
        cfg.pixels_per_meter = 12.5
        assert cfg.has_calibration()


class TestAnalysisSession:
    def test_lifecycle(self):
        s = AnalysisSession(id="sess1", source_id="cam_001")
        assert s.status == SessionStatus.PENDING
        s.mark_started()
        assert s.status == SessionStatus.RUNNING
        s.mark_completed()
        assert s.status == SessionStatus.COMPLETED
        assert s.finished_at is not None

    def test_failed(self):
        s = AnalysisSession(id="sess1", source_id="cam_001")
        s.mark_failed("boom")
        assert s.status == SessionStatus.FAILED
        assert s.error_message == "boom"

    def test_round_trip(self):
        s = AnalysisSession(id="sess1", source_id="cam_001", interval_seconds=15)
        s.mark_completed()
        restored = AnalysisSession.from_dict(s.to_dict())
        assert restored.id == s.id
        assert restored.status == SessionStatus.COMPLETED


class TestAnalysisResult:
    def test_aggregate(self):
        r = AnalysisResult(session_id="x", source_id="y")
        r.append(
            AnalysisInterval(
                timestamp=datetime(2026, 4, 29, 9, 0, 0),
                duration_seconds=30.0,
                vehicle_counts={"car": 5, "truck": 1},
            )
        )
        r.append(
            AnalysisInterval(
                timestamp=datetime(2026, 4, 29, 9, 0, 30),
                duration_seconds=30.0,
                vehicle_counts={"car": 3, "motorcycle": 4},
            )
        )
        assert r.total_count() == 13
        assert r.total_count_by_type() == {"car": 8, "truck": 1, "motorcycle": 4}


class TestVehicleTrack:
    def test_speed_zero_when_uncalibrated(self):
        car = VehicleType("car", pce=1.0)
        t = VehicleTrack(tracker_id=1, vehicle_type=car)
        t.add(TrackPoint(0, (0, 0), (0, 0, 10, 10)))
        t.add(TrackPoint(30, (300, 0), (300, 0, 310, 10)))
        assert t.speed_kmh(fps=30, pixels_per_meter=0) == 0.0

    def test_speed_known_displacement(self):
        car = VehicleType("car", pce=1.0)
        t = VehicleTrack(tracker_id=1, vehicle_type=car)
        # 30 frames @ 30fps = 1 second; 100 px / 10 px-per-m = 10 m -> 36 km/h
        t.add(TrackPoint(0, (0.0, 0.0), (0, 0, 10, 10)))
        t.add(TrackPoint(30, (100.0, 0.0), (100, 0, 110, 10)))
        speed = t.speed_kmh(fps=30, pixels_per_meter=10)
        assert abs(speed - 36.0) < 1e-6

    def test_speed_zero_with_one_point(self):
        car = VehicleType("car", pce=1.0)
        t = VehicleTrack(tracker_id=1, vehicle_type=car)
        t.add(TrackPoint(0, (0.0, 0.0), (0, 0, 10, 10)))
        assert t.speed_kmh(fps=30, pixels_per_meter=10) == 0.0
