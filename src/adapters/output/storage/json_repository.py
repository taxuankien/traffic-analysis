"""File-backed JSON repositories.

Layout:
    data/
        sources/sources.json              # registry list
        configs/<source_id>.json          # one config per source
        results/<source_id>/sessions.json # sessions list per source
"""
from __future__ import annotations

import json
from pathlib import Path

from src.application.ports.output.repository_port import (
    ROIConfigRepositoryPort,
    SessionRepositoryPort,
    SourceRepositoryPort,
)
from src.domain.entities.analysis_session import AnalysisSession
from src.domain.entities.roi_config import ROIConfig
from src.domain.entities.video_source import VideoSource
from src.domain.exceptions import (
    AnalysisSessionNotFoundError,
    ROIConfigNotFoundError,
    VideoSourceNotFoundError,
)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _read_json(p: Path, default):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, data) -> None:
    _ensure_dir(p.parent)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class JSONSourceRepository(SourceRepositoryPort):
    """Repo cho ``VideoSource``.

    Hợp đồng đường dẫn:
        - Khi lưu: nếu ``source.path`` tuyệt đối và nằm trong ``base_dir``, file
          JSON sẽ chứa path tương đối so với ``base_dir`` để project portable.
          Nếu nằm ngoài (trường hợp legacy), giữ nguyên tuyệt đối.
        - Khi đọc: luôn trả về path tuyệt đối, để mọi consumer (CLI/GUI/service)
          dùng được trực tiếp với cv2/IO mà không cần biết tới ``base_dir``.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir).resolve()
        self._file = self._base_dir / "sources" / "sources.json"

    def _to_stored(self, path: str) -> str:
        p = Path(path)
        if not p.is_absolute():
            return str(p)
        try:
            return str(p.relative_to(self._base_dir))
        except ValueError:
            return str(p)

    def _from_stored(self, path: str) -> str:
        p = Path(path)
        if p.is_absolute():
            return str(p)
        return str((self._base_dir / p).resolve())

    def _load_all(self) -> list[dict]:
        return _read_json(self._file, [])

    def _save_all(self, items: list[dict]) -> None:
        _write_json(self._file, items)

    def _hydrate(self, raw: dict) -> VideoSource:
        source = VideoSource.from_dict(raw)
        source.path = self._from_stored(source.path)
        return source

    def save(self, source: VideoSource) -> None:
        items = self._load_all()
        items = [i for i in items if i.get("id") != source.id]
        record = source.to_dict()
        record["path"] = self._to_stored(record["path"])
        items.append(record)
        self._save_all(items)

    def list_all(self) -> list[VideoSource]:
        return [self._hydrate(i) for i in self._load_all()]

    def get(self, source_id: str) -> VideoSource:
        for i in self._load_all():
            if i.get("id") == source_id:
                return self._hydrate(i)
        raise VideoSourceNotFoundError(f"VideoSource '{source_id}' not found")

    def delete(self, source_id: str) -> None:
        items = self._load_all()
        new_items = [i for i in items if i.get("id") != source_id]
        if len(new_items) == len(items):
            raise VideoSourceNotFoundError(f"VideoSource '{source_id}' not found")
        self._save_all(new_items)


class JSONROIConfigRepository(ROIConfigRepositoryPort):
    def __init__(self, base_dir: str | Path) -> None:
        self._dir = Path(base_dir) / "configs"

    def _path(self, source_id: str) -> Path:
        return self._dir / f"{source_id}.json"

    def save(self, config: ROIConfig) -> None:
        _write_json(self._path(config.source_id), config.to_dict())

    def load(self, source_id: str) -> ROIConfig:
        p = self._path(source_id)
        if not p.exists():
            raise ROIConfigNotFoundError(f"No ROI config for source '{source_id}'")
        return ROIConfig.from_dict(_read_json(p, {}))

    def get(self, source_id: str) -> ROIConfig:
        return self.load(source_id)

    def exists(self, source_id: str) -> bool:
        return self._path(source_id).exists()


class JSONSessionRepository(SessionRepositoryPort):
    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir) / "results"

    def _file(self, source_id: str) -> Path:
        return self._base / source_id / "sessions.json"

    def _load(self, source_id: str) -> list[dict]:
        return _read_json(self._file(source_id), [])

    def save(self, session: AnalysisSession) -> None:
        items = self._load(session.source_id)
        items = [i for i in items if i.get("id") != session.id]
        items.append(session.to_dict())
        _write_json(self._file(session.source_id), items)

    def list_for_source(self, source_id: str) -> list[AnalysisSession]:
        return [AnalysisSession.from_dict(i) for i in self._load(source_id)]

    def get(self, source_id: str, session_id: str) -> AnalysisSession:
        for i in self._load(source_id):
            if i.get("id") == session_id:
                return AnalysisSession.from_dict(i)
        raise AnalysisSessionNotFoundError(
            f"Session '{session_id}' not found for source '{source_id}'"
        )
