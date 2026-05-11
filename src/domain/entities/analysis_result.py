from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.value_objects.analysis_interval import AnalysisInterval


@dataclass
class AnalysisResult:
    session_id: str
    source_id: str
    intervals: list[AnalysisInterval] = field(default_factory=list)

    def append(self, interval: AnalysisInterval) -> None:
        self.intervals.append(interval)

    def total_count(self) -> int:
        return sum(i.total_count() for i in self.intervals)

    def total_count_by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for itv in self.intervals:
            for k, v in itv.vehicle_counts.items():
                out[k] = out.get(k, 0) + v
        return out
