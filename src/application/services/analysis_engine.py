"""Stateless metric calculators built on supervision zones.

Each helper takes a ``sv.Detections`` after tracking (i.e. with ``tracker_id`` populated)
and returns numeric metrics. They have no side effects beyond their internal counters
(LineZone counters are kept inside the supervision objects; the Speed tracker holds
centroid history).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

import numpy as np
import supervision as sv

from src.domain.entities.roi_config import ROIConfig
from src.domain.value_objects.analysis_interval import AnalysisInterval
from src.domain.value_objects.counting_line import CountingLine, LineDirection
from src.domain.value_objects.roi_polygon import ROIPolygon
from src.domain.value_objects.vehicle_type import COCO_TO_VEHICLE_TYPE


# --- Counting -------------------------------------------------------------

@dataclass
class LineCounter:
    """Wraps an sv.LineZone and keeps per-class crossing counts.

    Uses ``BOTTOM_CENTER`` as the only triggering anchor so that a crossing is registered
    the moment the bottom-center of a bbox passes the line — matching the behavior of
    ``supervision <= 0.24`` and the reference ``script.py``. The default in supervision
    >=0.25 requires all four corners to cross, which under-counts traffic that overlaps
    the line for several frames.
    """

    line: CountingLine
    zone: sv.LineZone
    counts_in: dict[str, int] = field(default_factory=dict)
    counts_out: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_config(cls, line: CountingLine) -> "LineCounter":
        kwargs: dict = {
            "start": sv.Point(*line.start),
            "end": sv.Point(*line.end),
        }
        # Newer supervision exposes triggering_anchors; older versions don't.
        try:
            kwargs["triggering_anchors"] = (sv.Position.BOTTOM_CENTER,)
            zone = sv.LineZone(**kwargs)
        except TypeError:
            kwargs.pop("triggering_anchors", None)
            zone = sv.LineZone(**kwargs)
        return cls(line=line, zone=zone)

    def update(self, detections: sv.Detections) -> tuple[dict[str, int], dict[str, int]]:
        """Run trigger and return ``(crossed_in_by_class, crossed_out_by_class)`` for *this* frame."""
        crossed_in_mask, crossed_out_mask = self.zone.trigger(detections)
        added_in: dict[str, int] = {}
        added_out: dict[str, int] = {}

        if detections.class_id is None:
            return added_in, added_out

        if self.line.direction in (LineDirection.IN, LineDirection.BOTH):
            for cid in detections.class_id[crossed_in_mask]:
                vt = COCO_TO_VEHICLE_TYPE.get(int(cid))
                if vt:
                    added_in[vt.name] = added_in.get(vt.name, 0) + 1
                    self.counts_in[vt.name] = self.counts_in.get(vt.name, 0) + 1
        if self.line.direction in (LineDirection.OUT, LineDirection.BOTH):
            for cid in detections.class_id[crossed_out_mask]:
                vt = COCO_TO_VEHICLE_TYPE.get(int(cid))
                if vt:
                    added_out[vt.name] = added_out.get(vt.name, 0) + 1
                    self.counts_out[vt.name] = self.counts_out.get(vt.name, 0) + 1
        return added_in, added_out


# --- Occupancy ------------------------------------------------------------

@dataclass
class OccupancyZone:
    polygon: ROIPolygon
    zone: sv.PolygonZone
    _zone_area: float = 0.0

    @classmethod
    def from_config(
        cls,
        polygon: ROIPolygon,
        frame_resolution_wh: tuple[int, int] | None = None,
    ) -> "OccupancyZone":
        pts = np.array(polygon.points, dtype=int)
        try:
            zone = sv.PolygonZone(polygon=pts)
        except TypeError:
            # Older sv versions require frame_resolution_wh
            zone = sv.PolygonZone(polygon=pts, frame_resolution_wh=frame_resolution_wh or (1, 1))
        return cls(polygon=polygon, zone=zone, _zone_area=_polygon_area(pts))

    def occupancy(self, detections: sv.Detections) -> tuple[float, np.ndarray]:
        if len(detections) == 0 or self._zone_area <= 0:
            return 0.0, np.array([], dtype=bool)
        in_zone_mask = self.zone.trigger(detections)
        xyxy = detections.xyxy
        bbox_areas = (xyxy[:, 2] - xyxy[:, 0]) * (xyxy[:, 3] - xyxy[:, 1])
        occupied = float(bbox_areas[in_zone_mask].sum())
        ratio = occupied / self._zone_area
        return min(max(ratio, 0.0), 1.0), in_zone_mask

    @property
    def area(self) -> float:
        return self._zone_area


def _polygon_area(points: np.ndarray) -> float:
    """Shoelace formula. ``points`` shape (N, 2)."""
    if points.shape[0] < 3:
        return 0.0
    x = points[:, 0].astype(float)
    y = points[:, 1].astype(float)
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


# --- Speed ----------------------------------------------------------------

@dataclass
class _CentroidHistory:
    first_frame: int
    last_frame: int
    first_centroid: tuple[float, float]
    last_centroid: tuple[float, float]
    samples: int = 1


class SpeedEstimator:
    """Estimate per-track speed from centroid displacement.

    Tracks visible for fewer than ``min_frames`` are treated as outliers and ignored.
    """

    def __init__(self, fps: float, pixels_per_meter: float, min_frames: int = 5) -> None:
        self.fps = fps
        self.pixels_per_meter = pixels_per_meter
        self.min_frames = min_frames
        self._history: dict[int, _CentroidHistory] = {}

    def update(self, detections: sv.Detections, frame_index: int) -> None:
        if detections.tracker_id is None or len(detections) == 0:
            return
        xyxy = detections.xyxy
        cx = (xyxy[:, 0] + xyxy[:, 2]) * 0.5
        cy = (xyxy[:, 1] + xyxy[:, 3]) * 0.5
        for i, tid in enumerate(detections.tracker_id):
            if tid is None:
                continue
            tid_int = int(tid)
            centroid = (float(cx[i]), float(cy[i]))
            hist = self._history.get(tid_int)
            if hist is None:
                self._history[tid_int] = _CentroidHistory(
                    first_frame=frame_index,
                    last_frame=frame_index,
                    first_centroid=centroid,
                    last_centroid=centroid,
                )
            else:
                hist.last_frame = frame_index
                hist.last_centroid = centroid
                hist.samples += 1

    def average_speed_kmh(self) -> float:
        if self.pixels_per_meter <= 0 or self.fps <= 0:
            return 0.0
        speeds: list[float] = []
        for h in self._history.values():
            if h.samples < self.min_frames:
                continue
            df = h.last_frame - h.first_frame
            if df <= 0:
                continue
            dx = h.last_centroid[0] - h.first_centroid[0]
            dy = h.last_centroid[1] - h.first_centroid[1]
            displacement_px = (dx * dx + dy * dy) ** 0.5
            meters = displacement_px / self.pixels_per_meter
            seconds = df / self.fps
            speeds.append((meters / seconds) * 3.6)
        if not speeds:
            return 0.0
        return float(sum(speeds) / len(speeds))

    def reset_window(self) -> None:
        """Clear history at the end of an interval."""
        self._history.clear()


# --- Queue detection ------------------------------------------------------

class QueueDetector:
    """Flag tracker_ids whose displacement over a rolling window stays below threshold.

    A track is "queued" when the camera-plane speed averaged over the last
    ``window_frames`` samples is below ``stopped_speed_kmh``. Requires a valid
    ``pixels_per_meter`` calibration; without it, queue detection is disabled.
    """

    def __init__(
        self,
        fps: float,
        pixels_per_meter: float,
        stopped_speed_kmh: float = 5.0,
        window_frames: int = 5,
    ) -> None:
        self.fps = float(fps)
        self.pixels_per_meter = float(pixels_per_meter)
        self.threshold_kmh = float(stopped_speed_kmh)
        self.window = max(2, int(window_frames))
        self._history: dict[int, deque[tuple[int, float, float]]] = {}

    def update(self, detections: sv.Detections, frame_index: int) -> None:
        if detections.tracker_id is None or len(detections) == 0:
            return
        xyxy = detections.xyxy
        cx = (xyxy[:, 0] + xyxy[:, 2]) * 0.5
        cy = (xyxy[:, 1] + xyxy[:, 3]) * 0.5
        for i, tid in enumerate(detections.tracker_id):
            if tid is None:
                continue
            tid_int = int(tid)
            history = self._history.get(tid_int)
            if history is None:
                history = deque(maxlen=self.window)
                self._history[tid_int] = history
            history.append((frame_index, float(cx[i]), float(cy[i])))

    def is_queued(self, tracker_id: int | None) -> bool:
        if tracker_id is None:
            return False
        if self.pixels_per_meter <= 0 or self.fps <= 0:
            return False
        history = self._history.get(int(tracker_id))
        if history is None or len(history) < 2:
            return False
        f0, x0, y0 = history[0]
        f1, x1, y1 = history[-1]
        if f1 <= f0:
            return True  # tracker visible only on a single frame — treat as stationary
        seconds = (f1 - f0) / self.fps
        dist_px = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        speed_kmh = (dist_px / self.pixels_per_meter) / seconds * 3.6
        return speed_kmh < self.threshold_kmh

    def reset(self) -> None:
        self._history.clear()


# --- Interval aggregator --------------------------------------------------

@dataclass
class IntervalAggregator:
    interval_seconds: float
    fps: float
    start_timestamp: datetime

    counts_in: dict[str, int] = field(default_factory=dict)
    counts_out: dict[str, int] = field(default_factory=dict)
    occupancy_samples: list[float] = field(default_factory=list)
    speed_samples: list[float] = field(default_factory=list)
    queue_samples: list[int] = field(default_factory=list)
    interval_index: int = 0

    @property
    def frames_per_interval(self) -> int:
        return max(1, int(round(self.interval_seconds * self.fps)))

    def add_line_counts(self, in_by_class: dict[str, int], out_by_class: dict[str, int]) -> None:
        for k, v in in_by_class.items():
            self.counts_in[k] = self.counts_in.get(k, 0) + v
        for k, v in out_by_class.items():
            self.counts_out[k] = self.counts_out.get(k, 0) + v

    def add_occupancy(self, ratio: float) -> None:
        self.occupancy_samples.append(ratio)

    def add_speed(self, kmh: float) -> None:
        if kmh > 0:
            self.speed_samples.append(kmh)

    def add_queue(self, count: int) -> None:
        self.queue_samples.append(int(count))

    def is_full(self, frame_in_interval: int) -> bool:
        return frame_in_interval >= self.frames_per_interval

    def flush(self) -> AnalysisInterval:
        # Snapshot per-direction breakdown — AnalysisInterval will merge them
        # internally so callers can read either ``counts_in``/``counts_out`` or
        # ``vehicle_counts`` (= IN + OUT).
        counts_in = dict(self.counts_in)
        counts_out = dict(self.counts_out)
        occupancy = float(np.mean(self.occupancy_samples)) if self.occupancy_samples else 0.0
        speed = float(np.mean(self.speed_samples)) if self.speed_samples else 0.0
        queue = int(round(float(np.mean(self.queue_samples)))) if self.queue_samples else 0
        from datetime import timedelta

        ts = self.start_timestamp + timedelta(seconds=self.interval_seconds * self.interval_index)
        itv = AnalysisInterval(
            timestamp=ts,
            duration_seconds=self.interval_seconds,
            counts_in=counts_in,
            counts_out=counts_out,
            occupancy_ratio=min(max(occupancy, 0.0), 1.0),
            avg_speed_kmh=max(speed, 0.0),
            queue_length=max(queue, 0),
        )
        self.counts_in.clear()
        self.counts_out.clear()
        self.occupancy_samples.clear()
        self.speed_samples.clear()
        self.queue_samples.clear()
        self.interval_index += 1
        return itv


def build_line_counters(config: ROIConfig) -> list[LineCounter]:
    return [LineCounter.from_config(l) for l in config.counting_lines]


def build_occupancy_zones(
    config: ROIConfig, frame_resolution_wh: tuple[int, int] | None = None
) -> list[OccupancyZone]:
    return [OccupancyZone.from_config(p, frame_resolution_wh) for p in config.roi_polygons]


def merge_count_dicts(dicts: Iterable[dict[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in dicts:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return out
