from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.exceptions import (
    CalibrationError,
    InvalidROIConfigError,
    InvalidVehicleTypeError,
)
from src.domain.value_objects import (
    AnalysisInterval,
    COCO_TO_VEHICLE_TYPE,
    CountingLine,
    LineDirection,
    ROIPolygon,
    VehicleType,
)


class TestROIPolygon:
    def test_minimum_points(self):
        p = ROIPolygon.from_points("lane_1", [(0, 0), (10, 0), (5, 10)])
        assert p.name == "lane_1"
        assert p.points == ((0, 0), (10, 0), (5, 10))

    def test_too_few_points_raises(self):
        with pytest.raises(InvalidROIConfigError):
            ROIPolygon.from_points("lane_1", [(0, 0), (10, 0)])

    def test_empty_name_raises(self):
        with pytest.raises(InvalidROIConfigError):
            ROIPolygon.from_points("", [(0, 0), (10, 0), (5, 10)])

    def test_round_trip_dict(self):
        original = ROIPolygon.from_points("lane_1", [(0, 0), (10, 0), (5, 10)])
        restored = ROIPolygon.from_dict(original.to_dict())
        assert original == restored


class TestCountingLine:
    def test_construct(self):
        line = CountingLine(
            "in_line", start=(0, 100), end=(200, 100), direction=LineDirection.IN
        )
        assert line.direction == LineDirection.IN

    def test_zero_length_raises(self):
        with pytest.raises(InvalidROIConfigError):
            CountingLine("bad", start=(0, 0), end=(0, 0))

    def test_dict_round_trip(self):
        line = CountingLine("l1", start=(0, 100), end=(200, 100), direction=LineDirection.OUT)
        restored = CountingLine.from_dict(line.to_dict())
        assert restored == line


class TestVehicleType:
    def test_pce_must_be_positive(self):
        with pytest.raises(InvalidVehicleTypeError):
            VehicleType("car", pce=0)

    def test_coco_mapping_complete(self):
        assert {2, 3, 5, 7} == set(COCO_TO_VEHICLE_TYPE.keys())
        names = {v.name for v in COCO_TO_VEHICLE_TYPE.values()}
        assert names == {"car", "motorcycle", "bus", "truck"}


class TestAnalysisInterval:
    def test_total_count(self):
        itv = AnalysisInterval(
            timestamp=datetime(2026, 4, 29, 9, 0, 0),
            duration_seconds=30.0,
            vehicle_counts={"car": 12, "motorcycle": 45, "bus": 1, "truck": 2},
            occupancy_ratio=0.35,
            avg_speed_kmh=28.5,
        )
        assert itv.total_count() == 60

    def test_invalid_occupancy_raises(self):
        with pytest.raises(ValueError):
            AnalysisInterval(
                timestamp=datetime.now(),
                duration_seconds=30.0,
                occupancy_ratio=1.2,
            )

    def test_invalid_duration_raises(self):
        with pytest.raises(ValueError):
            AnalysisInterval(
                timestamp=datetime.now(),
                duration_seconds=0,
            )
