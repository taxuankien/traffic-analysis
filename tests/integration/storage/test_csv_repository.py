from __future__ import annotations

from datetime import datetime, timedelta

from src.adapters.output.storage.csv_repository import CSVIntervalRepository
from src.domain.value_objects import AnalysisInterval


def _itv(ts: datetime, **counts) -> AnalysisInterval:
    return AnalysisInterval(
        timestamp=ts,
        duration_seconds=30.0,
        vehicle_counts=counts,
        occupancy_ratio=0.3,
        avg_speed_kmh=28.0,
    )


def test_csv_append_and_list(tmp_path):
    repo = CSVIntervalRepository(tmp_path)
    base = datetime(2026, 4, 29, 9, 0, 0)
    repo.append("cam_001", "sess1", _itv(base, car=12, motorcycle=45))
    repo.append(
        "cam_001",
        "sess1",
        _itv(base + timedelta(seconds=30), car=10, truck=2),
    )
    listed = repo.list("cam_001", "sess1")
    assert len(listed) == 2
    assert listed[0].vehicle_counts["car"] == 12
    assert listed[1].vehicle_counts["truck"] == 2


def test_csv_filter_by_time(tmp_path):
    repo = CSVIntervalRepository(tmp_path)
    base = datetime(2026, 4, 29, 9, 0, 0)
    repo.append("cam_001", "sess1", _itv(base, car=1))
    repo.append("cam_001", "sess1", _itv(base + timedelta(seconds=30), car=2))
    repo.append("cam_001", "sess1", _itv(base + timedelta(seconds=60), car=3))

    out = repo.list(
        "cam_001",
        "sess1",
        start=base + timedelta(seconds=15),
        end=base + timedelta(seconds=45),
    )
    assert [i.vehicle_counts["car"] for i in out] == [2]


def test_csv_empty_returns_empty(tmp_path):
    repo = CSVIntervalRepository(tmp_path)
    assert repo.list("nope", "nope") == []


def test_csv_round_trip_keeps_in_out_breakdown(tmp_path):
    repo = CSVIntervalRepository(tmp_path)
    ts = datetime(2026, 4, 29, 9, 0, 0)
    itv = AnalysisInterval(
        timestamp=ts,
        duration_seconds=30.0,
        counts_in={"car": 4, "motorcycle": 2},
        counts_out={"car": 1, "truck": 3},
        occupancy_ratio=0.42,
        avg_speed_kmh=35.0,
        queue_length=6,
    )
    repo.append("cam_001", "sess1", itv)
    [restored] = repo.list("cam_001", "sess1")

    assert restored.counts_in == {"car": 4, "motorcycle": 2}
    assert restored.counts_out == {"car": 1, "truck": 3}
    assert restored.vehicle_counts == {"car": 5, "motorcycle": 2, "truck": 3}
    assert restored.queue_length == 6
    # Header on disk includes all the new columns.
    csv_path = repo.csv_path("cam_001", "sess1")
    with open(csv_path, encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    for col in (
        "queue_length",
        "total_count",
        "total_pcu",
        "flow_rate_pcu",
        "car_in",
        "car_out",
        "motorcycle_in",
        "motorcycle_out",
        "bus_in",
        "bus_out",
        "truck_in",
        "truck_out",
    ):
        assert col in header, f"missing column {col} in {header}"
