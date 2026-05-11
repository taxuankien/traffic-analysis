from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.value_objects.vehicle_type import COCO_TO_VEHICLE_TYPE


def _merge(*dicts: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in dicts:
        if not d:
            continue
        for k, v in d.items():
            out[k] = out.get(k, 0) + int(v)
    return out


def _pce_for(name: str) -> float:
    """Lookup the current PCE value for a vehicle name. Falls back to 1.0 (car-equivalent)
    if the name is unknown so we never silently zero out a class."""
    for vt in COCO_TO_VEHICLE_TYPE.values():
        if vt.name == name:
            return float(vt.pce)
    return 1.0


@dataclass(frozen=True)
class AnalysisInterval:
    """Aggregated traffic metrics over a fixed time window.

    ``vehicle_counts`` is the per-class total (IN + OUT) and stays as the canonical
    field consumed by callers/tests. ``counts_in`` / ``counts_out`` carry the same
    breakdown split by crossing direction so dashboards & CSV can report them
    separately without losing information when both directions converge to one number.
    """

    timestamp: datetime
    duration_seconds: float
    vehicle_counts: dict[str, int] = field(default_factory=dict)
    counts_in: dict[str, int] = field(default_factory=dict)
    counts_out: dict[str, int] = field(default_factory=dict)
    occupancy_ratio: float = 0.0
    avg_speed_kmh: float = 0.0
    queue_length: int = 0

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0")
        if not (0.0 <= self.occupancy_ratio <= 1.0):
            raise ValueError(
                f"occupancy_ratio must be in [0.0, 1.0], got {self.occupancy_ratio}"
            )
        if self.avg_speed_kmh < 0:
            raise ValueError("avg_speed_kmh must be >= 0")
        if self.queue_length < 0:
            raise ValueError("queue_length must be >= 0")
        # If caller passed per-direction breakdown but no merged dict, derive it.
        if not self.vehicle_counts and (self.counts_in or self.counts_out):
            object.__setattr__(
                self, "vehicle_counts", _merge(self.counts_in, self.counts_out)
            )

    def total_count(self) -> int:
        return sum(self.vehicle_counts.values())

    @property
    def total_in(self) -> int:
        return sum(self.counts_in.values())

    @property
    def total_out(self) -> int:
        return sum(self.counts_out.values())

    def total_pcu(self) -> float:
        """Tổng lưu lượng quy đổi xe con (PCU) cho interval — dùng bảng PCE hiện hành."""
        return sum(count * _pce_for(name) for name, count in self.vehicle_counts.items())

    @property
    def flow_rate_pcu(self) -> float:
        """Lưu lượng quy đổi PCU/giờ (TCVN 4054).

        Khác với "vehicles per hour" thuần đếm số xe: mỗi loại xe nhân với hệ số PCE
        (xe máy 0.25–0.3, xe con 1.0, xe tải 2.5, xe bus 3.0...). Cấu hình PCE đặt
        trong ``config/inference.yaml`` (section ``vehicle_pce``).
        """
        if self.duration_seconds <= 0:
            return 0.0
        return self.total_pcu() * 3600.0 / float(self.duration_seconds)

    def to_row(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "occupancy_ratio": self.occupancy_ratio,
            "avg_speed_kmh": self.avg_speed_kmh,
            "queue_length": self.queue_length,
            "flow_rate_pcu": self.flow_rate_pcu,
            "total_pcu": self.total_pcu(),
            "total_count": self.total_count(),
            **self.vehicle_counts,
        }
