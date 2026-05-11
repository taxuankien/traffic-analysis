from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from src.application.ports.input.data_management_port import DataManagementPort
from src.application.ports.output.repository_port import (
    IntervalRepositoryPort,
    SessionRepositoryPort,
    SourceRepositoryPort,
)
from src.domain.entities.analysis_session import AnalysisSession
from src.domain.entities.video_source import VideoSource, VideoSourceKind
from src.domain.value_objects.analysis_interval import AnalysisInterval


class DataManagementService(DataManagementPort):
    def __init__(
        self,
        source_repo: SourceRepositoryPort,
        session_repo: SessionRepositoryPort,
        interval_repo: IntervalRepositoryPort,
        data_dir: Path | None = None,
    ) -> None:
        self._sources = source_repo
        self._sessions = session_repo
        self._intervals = interval_repo
        self._data_dir = Path(data_dir).resolve() if data_dir else None

    def _is_inside_data_dir(self, abs_path: Path) -> bool:
        if self._data_dir is None:
            return True
        try:
            abs_path.relative_to(self._data_dir)
            return True
        except ValueError:
            return False

    def _copy_into_data(self, abs_path: Path, source_id: str) -> Path:
        """Copy file từ ngoài data_dir vào data/sources/ để giữ project portable."""
        assert self._data_dir is not None
        sources_dir = self._data_dir / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)
        target = sources_dir / f"{source_id}_{abs_path.name}"
        shutil.copyfile(abs_path, target)
        return target

    def add_source(self, name: str, path: str) -> VideoSource:
        abs_path = Path(path).resolve()
        if not abs_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy file video: {abs_path}")

        source_id = f"src_{uuid.uuid4().hex[:10]}"
        # Phase 1: skip copy nếu file đã nằm trong data_dir (uploads/, ingested/, ...).
        # Web upload tạo file trực tiếp ở data/uploads/<source_id>_<orig> → tránh
        # copy thừa làm tốn disk gấp đôi cho video lớn.
        if self._data_dir is not None and not self._is_inside_data_dir(abs_path):
            abs_path = self._copy_into_data(abs_path, source_id)

        source = VideoSource(
            id=source_id,
            name=name,
            path=str(abs_path),
            kind=VideoSourceKind.FILE,
        )
        self._sources.save(source)
        return source

    def add_source_from_uploaded_path(
        self,
        name: str,
        uploaded_path: str | Path,
    ) -> VideoSource:
        """Đăng ký source khi file đã được web layer ghi vào ``data_dir/uploads/``.

        Khác với ``add_source``: KHÔNG copy/move file; chỉ tạo entry. Caller
        (router upload) đã chịu trách nhiệm validate và stream bytes vào
        ``uploaded_path`` đúng vị trí.
        """
        abs_path = Path(uploaded_path).resolve()
        if not abs_path.is_file():
            raise FileNotFoundError(f"Uploaded file không tồn tại: {abs_path}")
        if self._data_dir is not None and not self._is_inside_data_dir(abs_path):
            raise ValueError(
                f"Uploaded path phải nằm trong data_dir; got {abs_path}"
            )
        source_id = f"src_{uuid.uuid4().hex[:10]}"
        source = VideoSource(
            id=source_id,
            name=name,
            path=str(abs_path),
            kind=VideoSourceKind.FILE,
        )
        self._sources.save(source)
        return source

    def update_source(self, source: VideoSource) -> None:
        if self._data_dir is not None:
            abs_path = Path(source.path).resolve()
            if not self._is_inside_data_dir(abs_path):
                abs_path = self._copy_into_data(abs_path, source.id)
            source.path = str(abs_path)
        self._sources.save(source)

    def list_sources(self) -> list[VideoSource]:
        return self._sources.list_all()

    def get_source(self, source_id: str) -> VideoSource:
        return self._sources.get(source_id)

    def delete_source(self, source_id: str) -> None:
        self._sources.delete(source_id)

    def list_sessions(self, source_id: str) -> list[AnalysisSession]:
        return self._sessions.list_for_source(source_id)

    def query_intervals(
        self,
        source_id: str,
        session_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AnalysisInterval]:
        if session_id is not None:
            return self._intervals.list(source_id, session_id, start=start, end=end)
        out: list[AnalysisInterval] = []
        for sess in self._sessions.list_for_source(source_id):
            out.extend(self._intervals.list(source_id, sess.id, start=start, end=end))
        out.sort(key=lambda i: i.timestamp)
        return out

    def export_csv(self, source_id: str, session_id: str, target_path: str) -> str:
        src = Path(self._intervals.csv_path(source_id, session_id))
        if not src.exists():
            raise FileNotFoundError(f"No CSV at {src}")
        dst = Path(target_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        return str(dst)
