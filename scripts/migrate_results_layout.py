"""One-shot migration: results/<source_id>/<session_id>.csv → <session_id>/result.csv.

Idempotent — chạy lại nhiều lần không hỏng. Khi target folder đã tồn tại,
script chỉ log warning và bỏ qua entry đó.

Cách chạy:
    python -m scripts.migrate_results_layout                 # dùng TRAFFIC_DATA_DIR
    python -m scripts.migrate_results_layout --data-dir DIR  # explicit
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from src.bootstrap.paths import DEFAULT_DATA_DIR

logger = logging.getLogger(__name__)


def migrate(data_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    """Quét ``<data_dir>/results/`` và move các CSV phẳng vào folder per-session.

    Returns ``(moved, skipped)``.
    """
    results_root = data_dir / "results"
    if not results_root.is_dir():
        logger.info("Không có thư mục results tại %s — bỏ qua.", results_root)
        return (0, 0)

    moved = 0
    skipped = 0
    for source_dir in results_root.iterdir():
        if not source_dir.is_dir():
            continue
        for csv_file in source_dir.glob("*.csv"):
            session_id = csv_file.stem
            target_dir = source_dir / session_id
            target = target_dir / "result.csv"
            if target.exists():
                logger.warning(
                    "Bỏ qua %s — target %s đã tồn tại.", csv_file, target
                )
                skipped += 1
                continue
            if dry_run:
                logger.info("[DRY-RUN] %s → %s", csv_file, target)
                moved += 1
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(csv_file), str(target))
            logger.info("Đã move %s → %s", csv_file, target)
            moved += 1
    return (moved, skipped)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Đường dẫn data dir (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ log, không thực sự move file.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    data_dir = args.data_dir.expanduser().resolve()
    logger.info("Migrate results layout in %s%s", data_dir, " (dry-run)" if args.dry_run else "")
    moved, skipped = migrate(data_dir, dry_run=args.dry_run)
    logger.info("Done. Moved=%d  Skipped=%d", moved, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
