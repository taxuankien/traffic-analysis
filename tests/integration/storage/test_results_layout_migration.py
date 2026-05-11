"""Phase 1: ``CSVIntervalRepository`` ghi vào layout mới + migration script idempotent."""
from __future__ import annotations

from datetime import datetime

from src.adapters.output.storage.csv_repository import CSVIntervalRepository
from src.domain.value_objects.analysis_interval import AnalysisInterval
from scripts.migrate_results_layout import migrate


def _make_interval(seconds_offset: int = 0):
    return AnalysisInterval(
        timestamp=datetime(2026, 5, 1, 9, 0, seconds_offset),
        duration_seconds=30.0,
        vehicle_counts={"car": 5},
    )


def test_append_writes_to_new_per_session_folder(tmp_path):
    repo = CSVIntervalRepository(tmp_path)
    repo.append("src_a", "sess_1", _make_interval())

    new_path = tmp_path / "results" / "src_a" / "sess_1" / "result.csv"
    assert new_path.is_file()
    assert repo.csv_path("src_a", "sess_1") == str(new_path)


def test_csv_path_falls_back_to_legacy_when_only_legacy_exists(tmp_path):
    legacy_dir = tmp_path / "results" / "src_b"
    legacy_dir.mkdir(parents=True)
    legacy = legacy_dir / "sess_legacy.csv"
    legacy.write_text("timestamp,duration_seconds\n2026-05-01T09:00:00,30.0\n", encoding="utf-8")

    repo = CSVIntervalRepository(tmp_path)
    assert repo.csv_path("src_b", "sess_legacy") == str(legacy)


def test_list_reads_new_layout(tmp_path):
    repo = CSVIntervalRepository(tmp_path)
    repo.append("src_c", "sess_x", _make_interval())
    out = repo.list("src_c", "sess_x")
    assert len(out) == 1
    # CSV reader fills 0 for absent classes; the meaningful invariant is that
    # only the populated class shows a non-zero count.
    counts = out[0].vehicle_counts
    assert counts.get("car") == 5
    assert all(v == 0 for k, v in counts.items() if k != "car")


def test_migration_moves_legacy_csv_to_new_folder(tmp_path):
    src_dir = tmp_path / "results" / "src_z"
    src_dir.mkdir(parents=True)
    legacy = src_dir / "sess_old.csv"
    legacy.write_text("dummy", encoding="utf-8")

    moved, skipped = migrate(tmp_path)

    assert moved == 1
    assert skipped == 0
    assert not legacy.exists()
    assert (src_dir / "sess_old" / "result.csv").is_file()


def test_migration_is_idempotent(tmp_path):
    src_dir = tmp_path / "results" / "src_z"
    src_dir.mkdir(parents=True)
    (src_dir / "sess_old.csv").write_text("dummy", encoding="utf-8")
    migrate(tmp_path)
    moved, skipped = migrate(tmp_path)  # second run
    assert moved == 0


def test_migration_skips_when_target_already_exists(tmp_path):
    src_dir = tmp_path / "results" / "src_z"
    target_dir = src_dir / "sess_dup"
    target_dir.mkdir(parents=True)
    (target_dir / "result.csv").write_text("existing", encoding="utf-8")
    legacy = src_dir / "sess_dup.csv"
    legacy.write_text("legacy", encoding="utf-8")

    moved, skipped = migrate(tmp_path)
    assert moved == 0
    assert skipped == 1
    assert legacy.exists()  # not moved
