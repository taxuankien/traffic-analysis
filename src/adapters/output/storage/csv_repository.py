"""CSV-backed interval repository.

Layout (Phase 1 web-migration):
    data/results/<source_id>/<session_id>/result.csv

Layout cũ (legacy, vẫn đọc được):
    data/results/<source_id>/<session_id>.csv

Khi đọc, repo tự fallback sang đường dẫn cũ nếu folder mới không tồn tại,
nên user không bắt buộc chạy migration ngay. Khi ghi, luôn dùng layout mới.

Columns (in this order):
    timestamp, duration_seconds, occupancy_ratio, avg_speed_kmh,
    queue_length, total_count, total_pcu, flow_rate_pcu,
    car, motorcycle, bus, truck,                     # IN + OUT (legacy column names)
    car_in, car_out, motorcycle_in, motorcycle_out,  # per-direction breakdown
    bus_in, bus_out, truck_in, truck_out

``flow_rate_pcu`` là lưu lượng quy đổi xe con (PCU/giờ) theo TCVN 4054 — mỗi
loại xe nhân với hệ số PCE (cấu hình trong ``config/inference.yaml``). Khác
với cách đếm thuần "xe/giờ", PCU phản ánh đúng năng lực thông qua của làn.

Per-direction columns let dashboards distinguish inbound vs outbound flow even
when a counting line is configured ``direction=both``. The legacy ``car``,
``motorcycle``, ``bus``, ``truck`` columns remain so older readers (Excel
templates, notebooks) keep working.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from src.application.ports.output.repository_port import IntervalRepositoryPort
from src.domain.value_objects.analysis_interval import AnalysisInterval
from src.domain.value_objects.vehicle_type import COCO_TO_VEHICLE_TYPE

DEFAULT_VEHICLE_COLUMNS = sorted({v.name for v in COCO_TO_VEHICLE_TYPE.values()})
BASE_COLUMNS = [
    "timestamp",
    "duration_seconds",
    "occupancy_ratio",
    "avg_speed_kmh",
    "queue_length",
    "total_count",
    "total_pcu",
    "flow_rate_pcu",
]
DIRECTION_SUFFIXES = ("_in", "_out")


class CSVIntervalRepository(IntervalRepositoryPort):
    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir) / "results"

    def session_dir(self, source_id: str, session_id: str) -> Path:
        """Folder chứa toàn bộ artifacts của session (csv, summary, video, frames)."""
        return self._base / source_id / session_id

    def csv_path(self, source_id: str, session_id: str) -> str:
        """Path đến CSV — ưu tiên layout mới, fallback layout cũ nếu chỉ có legacy file.

        Khi gọi để **đọc**: cần kiểm tra ``Path(...).exists()`` ở caller.
        Khi gọi để **ghi**: dùng ``_write_path()`` để luôn ép layout mới.
        """
        new = self.session_dir(source_id, session_id) / "result.csv"
        if new.exists():
            return str(new)
        legacy = self._base / source_id / f"{session_id}.csv"
        if legacy.exists():
            return str(legacy)
        return str(new)  # default to new for create-on-write

    def _write_path(self, source_id: str, session_id: str) -> Path:
        return self.session_dir(source_id, session_id) / "result.csv"

    def _path(self, source_id: str, session_id: str) -> Path:
        return Path(self.csv_path(source_id, session_id))

    def _columns(self) -> list[str]:
        directional = [f"{v}{suffix}" for v in DEFAULT_VEHICLE_COLUMNS for suffix in DIRECTION_SUFFIXES]
        return BASE_COLUMNS + DEFAULT_VEHICLE_COLUMNS + directional

    def append(self, source_id: str, session_id: str, interval: AnalysisInterval) -> None:
        p = self._write_path(source_id, session_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        cols = self._columns()
        new_file = not p.exists()
        with p.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            if new_file:
                w.writeheader()
            row: dict[str, object] = {c: 0 for c in cols}
            row["timestamp"] = interval.timestamp.isoformat()
            row["duration_seconds"] = interval.duration_seconds
            row["occupancy_ratio"] = round(interval.occupancy_ratio, 4)
            row["avg_speed_kmh"] = round(interval.avg_speed_kmh, 2)
            row["queue_length"] = interval.queue_length
            row["total_count"] = interval.total_count()
            row["total_pcu"] = round(interval.total_pcu(), 3)
            row["flow_rate_pcu"] = round(interval.flow_rate_pcu, 2)
            for k, v in interval.vehicle_counts.items():
                if k in cols:
                    row[k] = v
            for k, v in interval.counts_in.items():
                col = f"{k}_in"
                if col in cols:
                    row[col] = v
            for k, v in interval.counts_out.items():
                col = f"{k}_out"
                if col in cols:
                    row[col] = v
            w.writerow(row)

    def list(
        self,
        source_id: str,
        session_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AnalysisInterval]:
        p = self._path(source_id, session_id)
        if not p.exists():
            return []
        out: list[AnalysisInterval] = []
        with p.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = datetime.fromisoformat(row["timestamp"])
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue
                counts_in = self._collect_directional(row, "_in")
                counts_out = self._collect_directional(row, "_out")
                if counts_in or counts_out:
                    counts = self._merge(counts_in, counts_out)
                else:
                    # Legacy CSVs without _in/_out columns — fall back to merged total.
                    counts = {
                        c: int(row[c])
                        for c in row.keys()
                        if c in DEFAULT_VEHICLE_COLUMNS and row.get(c)
                    }
                out.append(
                    AnalysisInterval(
                        timestamp=ts,
                        duration_seconds=float(row["duration_seconds"]),
                        vehicle_counts=counts,
                        counts_in=counts_in,
                        counts_out=counts_out,
                        occupancy_ratio=float(row.get("occupancy_ratio", 0) or 0),
                        avg_speed_kmh=float(row.get("avg_speed_kmh", 0) or 0),
                        queue_length=int(float(row.get("queue_length", 0) or 0)),
                    )
                )
        return out

    @staticmethod
    def _collect_directional(row: dict, suffix: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for v in DEFAULT_VEHICLE_COLUMNS:
            col = f"{v}{suffix}"
            raw = row.get(col)
            if raw in (None, ""):
                continue
            try:
                value = int(float(raw))
            except (TypeError, ValueError):
                continue
            if value:
                out[v] = value
        return out

    @staticmethod
    def _merge(*dicts: dict[str, int]) -> dict[str, int]:
        merged: dict[str, int] = {}
        for d in dicts:
            for k, v in d.items():
                merged[k] = merged.get(k, 0) + int(v)
        return merged
