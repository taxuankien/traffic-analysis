from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.value_objects.vehicle_type import VehicleType


@dataclass
class TrackPoint:
    frame_index: int
    centroid: tuple[float, float]
    bbox: tuple[float, float, float, float]


@dataclass
class VehicleTrack:
    tracker_id: int
    vehicle_type: VehicleType
    points: list[TrackPoint] = field(default_factory=list)

    def add(self, point: TrackPoint) -> None:
        self.points.append(point)

    def first_seen_frame(self) -> int | None:
        return self.points[0].frame_index if self.points else None

    def last_seen_frame(self) -> int | None:
        return self.points[-1].frame_index if self.points else None

    def displacement_pixels(self) -> float:
        if len(self.points) < 2:
            return 0.0
        x0, y0 = self.points[0].centroid
        x1, y1 = self.points[-1].centroid
        return ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5

    def speed_kmh(self, fps: float, pixels_per_meter: float) -> float:
        if pixels_per_meter <= 0 or fps <= 0:
            return 0.0
        if len(self.points) < 2:
            return 0.0
        delta_frames = self.points[-1].frame_index - self.points[0].frame_index
        if delta_frames <= 0:
            return 0.0
        delta_pixels = self.displacement_pixels()
        meters = delta_pixels / pixels_per_meter
        seconds = delta_frames / fps
        return (meters / seconds) * 3.6
