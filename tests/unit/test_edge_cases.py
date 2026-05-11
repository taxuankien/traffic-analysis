from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest
import supervision as sv

from src.application.services.analysis_engine import (
    IntervalAggregator,
    OccupancyZone,
    SpeedEstimator,
)
from src.domain.value_objects import ROIPolygon


def _empty_detections() -> sv.Detections:
    return sv.Detections(
        xyxy=np.zeros((0, 4)),
        class_id=np.array([], dtype=int),
        confidence=np.array([], dtype=float),
    )


def test_occupancy_with_no_detections():
    poly = ROIPolygon.from_points("z1", [(0, 0), (100, 0), (50, 100)])
    zone = OccupancyZone.from_config(poly, frame_resolution_wh=(100, 100))
    ratio, _ = zone.occupancy(_empty_detections())
    assert ratio == 0.0


def test_speed_with_no_detections():
    est = SpeedEstimator(fps=30, pixels_per_meter=10, min_frames=2)
    est.update(_empty_detections(), 0)
    assert est.average_speed_kmh() == 0.0


def test_aggregator_flush_with_no_data():
    agg = IntervalAggregator(
        interval_seconds=30.0, fps=30.0, start_timestamp=datetime(2026, 4, 29, 9, 0, 0)
    )
    itv = agg.flush()
    assert itv.total_count() == 0
    assert itv.occupancy_ratio == 0.0
    assert itv.avg_speed_kmh == 0.0


def test_polygon_outside_frame_does_not_crash():
    poly = ROIPolygon.from_points("z1", [(2000, 2000), (2100, 2000), (2050, 2100)])
    zone = OccupancyZone.from_config(poly, frame_resolution_wh=(800, 600))
    det = sv.Detections(
        xyxy=np.array([[10, 10, 30, 30]], dtype=float),
        class_id=np.array([2], dtype=int),
        confidence=np.array([0.9]),
    )
    ratio, _ = zone.occupancy(det)
    assert ratio == 0.0
