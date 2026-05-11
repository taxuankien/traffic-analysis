from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest
import supervision as sv

from src.application.services.analysis_engine import (
    IntervalAggregator,
    LineCounter,
    OccupancyZone,
    QueueDetector,
    SpeedEstimator,
    _polygon_area,
)
from src.domain.value_objects import (
    CountingLine,
    LineDirection,
    ROIPolygon,
)


def _make_detections(
    bboxes: list[tuple[float, float, float, float]],
    class_ids: list[int],
    tracker_ids: list[int] | None = None,
) -> sv.Detections:
    xyxy = np.array(bboxes, dtype=float) if bboxes else np.zeros((0, 4))
    cls = np.array(class_ids, dtype=int) if class_ids else np.array([], dtype=int)
    conf = np.ones(len(class_ids), dtype=float) if class_ids else np.array([], dtype=float)
    det = sv.Detections(xyxy=xyxy, class_id=cls, confidence=conf)
    if tracker_ids is not None:
        det.tracker_id = np.array(tracker_ids, dtype=int)
    return det


def test_polygon_area_square():
    pts = np.array([[0, 0], [10, 0], [10, 10], [0, 10]])
    assert _polygon_area(pts) == 100.0


class TestLineCounter:
    def test_count_in_by_class(self):
        line = CountingLine(
            "in", start=(0, 100), end=(200, 100), direction=LineDirection.BOTH
        )
        counter = LineCounter.from_config(line)

        # Class 2 = car. Object centroid moves from y=50 to y=150 (crosses y=100 going down).
        d1 = _make_detections([(50, 30, 70, 70)], [2], [1])
        d2 = _make_detections([(50, 130, 70, 170)], [2], [1])
        counter.update(d1)
        in1, out1 = counter.update(d2)
        # Total in/out across both directions should be 1
        assert (sum(in1.values()) + sum(out1.values())) == 1
        assert (counter.counts_in.get("car", 0) + counter.counts_out.get("car", 0)) == 1


class TestOccupancyZone:
    def test_occupancy_ratio(self):
        poly = ROIPolygon.from_points("z1", [(0, 0), (100, 0), (100, 100), (0, 100)])
        zone = OccupancyZone.from_config(poly, frame_resolution_wh=(100, 100))
        assert abs(zone.area - 10000.0) < 1e-6

        det = _make_detections([(10, 10, 30, 30)], [2], [1])
        ratio, mask = zone.occupancy(det)
        assert abs(ratio - (20 * 20) / 10000) < 1e-3

    def test_occupancy_empty(self):
        poly = ROIPolygon.from_points("z1", [(0, 0), (100, 0), (50, 100)])
        zone = OccupancyZone.from_config(poly, frame_resolution_wh=(100, 100))
        det = _make_detections([], [], [])
        ratio, mask = zone.occupancy(det)
        assert ratio == 0.0


class TestSpeedEstimator:
    def test_known_speed_30fps_10ppm(self):
        est = SpeedEstimator(fps=30, pixels_per_meter=10, min_frames=2)
        # Track 1 starts at (0,0) at frame 0, ends at (300,0) at frame 30.
        # 30 frames @ 30fps = 1 sec. 300px / 10 = 30 m -> 108 km/h
        d0 = _make_detections([(-10, -10, 10, 10)], [2], [1])
        est.update(d0, 0)
        d1 = _make_detections([(290, -10, 310, 10)], [2], [1])
        est.update(d1, 30)
        assert abs(est.average_speed_kmh() - 108.0) < 1.0

    def test_returns_zero_without_calibration(self):
        est = SpeedEstimator(fps=30, pixels_per_meter=0, min_frames=2)
        d0 = _make_detections([(0, 0, 10, 10)], [2], [1])
        d1 = _make_detections([(100, 0, 110, 10)], [2], [1])
        est.update(d0, 0)
        est.update(d1, 30)
        assert est.average_speed_kmh() == 0.0


class TestIntervalAggregator:
    def test_flush(self):
        agg = IntervalAggregator(
            interval_seconds=30.0,
            fps=30.0,
            start_timestamp=datetime(2026, 4, 29, 9, 0, 0),
        )
        agg.add_line_counts({"car": 5}, {"motorcycle": 3})
        agg.add_occupancy(0.2)
        agg.add_occupancy(0.4)
        agg.add_speed(30.0)

        itv = agg.flush()
        assert itv.vehicle_counts["car"] == 5
        assert itv.vehicle_counts["motorcycle"] == 3
        assert abs(itv.occupancy_ratio - 0.3) < 1e-6
        assert itv.avg_speed_kmh == 30.0

    def test_flush_keeps_in_out_separated(self):
        agg = IntervalAggregator(
            interval_seconds=30.0,
            fps=30.0,
            start_timestamp=datetime(2026, 4, 29, 9, 0, 0),
        )
        agg.add_line_counts({"car": 4}, {"car": 2, "motorcycle": 1})
        agg.add_queue(7)
        agg.add_queue(9)

        itv = agg.flush()
        assert itv.counts_in == {"car": 4}
        assert itv.counts_out == {"car": 2, "motorcycle": 1}
        # vehicle_counts is the IN+OUT total
        assert itv.vehicle_counts == {"car": 6, "motorcycle": 1}
        assert itv.total_count() == 7
        # PCU = 6*1.0 (car) + 1*0.3 (motorcycle PCE default) = 6.3
        # flow_rate_pcu = 6.3 * 3600 / 30 = 756 PCU/h
        assert abs(itv.total_pcu() - 6.3) < 1e-6
        assert abs(itv.flow_rate_pcu - 756.0) < 1e-6
        assert itv.queue_length == 8  # round(mean(7,9))

    def test_flush_resets_state(self):
        agg = IntervalAggregator(
            interval_seconds=10.0, fps=30.0, start_timestamp=datetime(2026, 4, 29, 9, 0, 0)
        )
        agg.add_line_counts({"car": 2}, {})
        agg.add_queue(5)
        agg.flush()
        # Second flush should produce an empty interval (no accumulation leak).
        itv2 = agg.flush()
        assert itv2.total_count() == 0
        assert itv2.counts_in == {}
        assert itv2.counts_out == {}
        assert itv2.queue_length == 0


class TestQueueDetector:
    def test_stationary_track_is_queued(self):
        det = QueueDetector(
            fps=30.0, pixels_per_meter=10.0, stopped_speed_kmh=5.0, window_frames=5
        )
        # Centroid stays put — speed 0 km/h.
        for f in range(6):
            d = _make_detections([(100, 100, 110, 110)], [2], [42])
            det.update(d, f)
        assert det.is_queued(42) is True

    def test_moving_track_is_not_queued(self):
        det = QueueDetector(
            fps=30.0, pixels_per_meter=10.0, stopped_speed_kmh=5.0, window_frames=5
        )
        # 50 px movement over 5 frames @ 30fps, ppm=10 -> 5m / 0.167s = 30 m/s ≈ 108 km/h.
        for i, f in enumerate(range(6)):
            d = _make_detections([(i * 10, 100, i * 10 + 10, 110)], [2], [99])
            det.update(d, f)
        assert det.is_queued(99) is False

    def test_disabled_without_calibration(self):
        det = QueueDetector(
            fps=30.0, pixels_per_meter=0.0, stopped_speed_kmh=5.0, window_frames=5
        )
        for f in range(6):
            d = _make_detections([(100, 100, 110, 110)], [2], [42])
            det.update(d, f)
        # Without calibration we cannot reason about real-world speed → not queued.
        assert det.is_queued(42) is False
