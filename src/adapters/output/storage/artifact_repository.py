"""Filesystem implementation cho ``ArtifactRepositoryPort``.

Layout đích (Phase 1 web migration):
    data/results/<source_id>/<session_id>/
        result.csv         → kind=csv
        annotated.mp4      → kind=video (chỉ khi render_video=true)
        summary.json       → kind=summary
        frames/*.png       → kind=frame
    data/configs/<source_id>.json → kind=roi (per-source)
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.application.ports.output.artifact_repository_port import (
    Artifact,
    ArtifactKind,
    ArtifactRepositoryPort,
)


_KIND_FILENAME: dict[ArtifactKind, str] = {
    "csv": "result.csv",
    "video": "annotated.mp4",
    "summary": "summary.json",
}


class FileSystemArtifactRepository(ArtifactRepositoryPort):
    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)

    # --- public --------------------------------------------------------------

    def list_for_session(self, source_id: str, session_id: str) -> list[Artifact]:
        out: list[Artifact] = []
        for kind in ("csv", "video", "summary"):
            art = self._session_artifact(source_id, session_id, kind)  # type: ignore[arg-type]
            if art is not None:
                out.append(art)

        # Frames inside session folder (legacy: frames live in data/frames/
        # with prefix <source_id>_; here we focus on session-scoped frames).
        frames_dir = self._session_dir(source_id, session_id) / "frames"
        if frames_dir.is_dir():
            for f in sorted(frames_dir.glob("*.png")):
                stat = f.stat()
                out.append(
                    Artifact(
                        kind="frame",
                        name=f.name,
                        path=f,
                        size_bytes=stat.st_size,
                        mtime=datetime.fromtimestamp(stat.st_mtime),
                    )
                )

        roi = self.get_roi(source_id)
        if roi is not None:
            out.append(roi)
        return out

    def get(
        self, source_id: str, session_id: str, kind: ArtifactKind
    ) -> Artifact | None:
        if kind == "roi":
            return self.get_roi(source_id)
        return self._session_artifact(source_id, session_id, kind)

    def get_roi(self, source_id: str) -> Artifact | None:
        path = self._data_dir / "configs" / f"{source_id}.json"
        return self._artifact_or_none(path, kind="roi", name="roi.json")

    # --- internals -----------------------------------------------------------

    def _session_dir(self, source_id: str, session_id: str) -> Path:
        return self._data_dir / "results" / source_id / session_id

    def _session_artifact(
        self, source_id: str, session_id: str, kind: ArtifactKind
    ) -> Artifact | None:
        if kind not in _KIND_FILENAME:
            return None
        fname = _KIND_FILENAME[kind]
        path = self._session_dir(source_id, session_id) / fname
        if not path.is_file():
            # CSV legacy fallback: <session_id>.csv flat in source folder.
            if kind == "csv":
                legacy = self._data_dir / "results" / source_id / f"{session_id}.csv"
                if legacy.is_file():
                    return self._artifact_or_none(legacy, kind="csv", name="result.csv")
            return None
        return self._artifact_or_none(path, kind=kind, name=fname)

    @staticmethod
    def _artifact_or_none(
        path: Path, kind: ArtifactKind, name: str
    ) -> Artifact | None:
        if not path.is_file():
            return None
        stat = path.stat()
        return Artifact(
            kind=kind,
            name=name,
            path=path,
            size_bytes=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime),
        )
