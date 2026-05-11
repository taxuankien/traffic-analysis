"""Download artifacts: CSV / video / summary / ROI / bundle ZIP."""
from __future__ import annotations

import logging
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse

from src.adapters.input.web.deps import get_container
from src.adapters.input.web.schemas.artifact import ArtifactInfo
from src.application.ports.output.artifact_repository_port import (
    Artifact,
    ArtifactKind,
)
from src.bootstrap.container import Container
from src.domain.entities.analysis_session import AnalysisSession, SessionStatus
from src.domain.exceptions import AnalysisSessionNotFoundError

router = APIRouter(tags=["downloads"])
logger = logging.getLogger(__name__)


def _find_session(container: Container, session_id: str) -> AnalysisSession:
    for src in container.source_repo.list_all():
        try:
            return container.session_repo.get(src.id, session_id)
        except AnalysisSessionNotFoundError:
            continue
    raise AnalysisSessionNotFoundError(f"Session '{session_id}' không tìm thấy.")


def _to_info(art: Artifact, session_id: str | None) -> ArtifactInfo:
    if art.kind == "roi":
        url = f"/api/sources/{_extract_source_from_roi(art.path)}/download/roi.json"
    elif art.kind == "frame":
        # Frame artifact path lives inside session folder; expose via static mount.
        url = f"/files/{art.path.as_posix().split('/data/', 1)[-1]}"
    else:
        assert session_id is not None
        url = f"/api/sessions/{session_id}/download/{art.kind}"
    preview = url if art.kind == "video" else None
    return ArtifactInfo(
        kind=art.kind,
        name=art.name,
        size_bytes=art.size_bytes,
        mtime=art.mtime,
        download_url=url,
        preview_url=preview,
    )


def _extract_source_from_roi(path) -> str:
    return path.stem  # configs/<source_id>.json → source_id


@router.get(
    "/sessions/{session_id}/artifacts",
    response_model=list[ArtifactInfo],
)
def list_artifacts(
    session_id: str, container: Container = Depends(get_container)
) -> list[ArtifactInfo]:
    session = _find_session(container, session_id)
    arts = container.artifact_repo().list_for_session(session.source_id, session_id)
    return [_to_info(a, session_id=session_id) for a in arts]


@router.get("/sessions/{session_id}/download/csv")
def download_csv(
    session_id: str, container: Container = Depends(get_container)
) -> FileResponse:
    session = _find_session(container, session_id)
    art = container.artifact_repo().get(session.source_id, session_id, "csv")
    _require_artifact(session, art, "csv")
    return FileResponse(
        path=art.path,
        media_type="text/csv",
        filename=f"{session.source_id}_{session_id}.csv",
    )


@router.get("/sessions/{session_id}/download/summary")
def download_summary(
    session_id: str, container: Container = Depends(get_container)
) -> FileResponse:
    session = _find_session(container, session_id)
    art = container.artifact_repo().get(session.source_id, session_id, "summary")
    _require_artifact(session, art, "summary")
    return FileResponse(
        path=art.path,
        media_type="application/json",
        filename=f"{session.source_id}_{session_id}_summary.json",
    )


@router.post("/sessions/{session_id}/render-video", status_code=status.HTTP_202_ACCEPTED)
def render_video_now(
    session_id: str,
    request: Request,
    container: Container = Depends(get_container),
) -> dict:
    """Render annotated video sau khi session đã kết thúc.

    Hữu ích khi user không bật ``render_video=true`` lúc start hoặc file
    annotated bị xoá thủ công và muốn tạo lại. Job chạy async; client có thể
    poll ``/api/sessions/{id}/artifacts`` hoặc subscribe WS để nhận
    ``artifact_ready``.
    """
    session = _find_session(container, session_id)
    jobs = getattr(request.app.state, "jobs", None)
    if jobs is None:
        raise HTTPException(503, "JobManager chưa khởi động.")
    try:
        target = jobs.start_render(session.source_id, session_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "session_id": session_id,
        "status": jobs.render_status(session_id),
        "target": target,
        "download_url": f"/api/sessions/{session_id}/download/video",
    }


@router.get("/sessions/{session_id}/render-video", status_code=status.HTTP_200_OK)
def render_video_status(
    session_id: str, request: Request, container: Container = Depends(get_container)
) -> dict:
    session = _find_session(container, session_id)
    jobs = getattr(request.app.state, "jobs", None)
    return {
        "session_id": session_id,
        "status": jobs.render_status(session_id) if jobs else "idle",
        "available": container.artifact_repo().get(session.source_id, session_id, "video")
        is not None,
    }


@router.get("/sessions/{session_id}/download/video", response_model=None)
def download_video(
    session_id: str,
    container: Container = Depends(get_container),
) -> StreamingResponse | FileResponse:
    session = _find_session(container, session_id)
    art = container.artifact_repo().get(session.source_id, session_id, "video")
    if art is None:
        # Distinguish 425 (still rendering / pre-completion) vs 404 (never requested).
        if session.status in (SessionStatus.PENDING, SessionStatus.RUNNING):
            raise HTTPException(
                status.HTTP_425_TOO_EARLY,
                "Video chưa sẵn sàng — phiên đang chạy/render.",
            )
        raise HTTPException(404, "Video annotated không có cho session này.")
    return FileResponse(
        path=art.path,
        media_type="video/mp4",
        filename=f"annotated_{session_id}.mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/sessions/{session_id}/frames/{frame_name}", response_model=None)
def download_session_frame(
    session_id: str,
    frame_name: str,
    container: Container = Depends(get_container),
) -> FileResponse:
    """Tải 1 file frame PNG nằm trong session folder.

    Bảo vệ path traversal: ``frame_name`` không được chứa '..' hoặc '/'.
    """
    if ".." in frame_name or "/" in frame_name or "\\" in frame_name:
        raise HTTPException(400, "Tên frame không hợp lệ.")
    session = _find_session(container, session_id)
    frame_path = (
        container.data_dir
        / "results"
        / session.source_id
        / session_id
        / "frames"
        / frame_name
    )
    if not frame_path.is_file():
        raise HTTPException(404, f"Frame '{frame_name}' không có trong session.")
    return FileResponse(path=frame_path, media_type="image/png", filename=frame_name)


@router.get("/sources/{source_id}/download/roi.json")
def download_roi(
    source_id: str, container: Container = Depends(get_container)
) -> FileResponse:
    container.source_repo.get(source_id)  # 404 nếu source không có
    art = container.artifact_repo().get_roi(source_id)
    if art is None:
        raise HTTPException(404, f"Chưa có ROI config cho source '{source_id}'.")
    return FileResponse(
        path=art.path, media_type="application/json", filename=f"roi_{source_id}.json"
    )


@router.get("/sessions/{session_id}/download/bundle.zip")
def download_bundle(
    session_id: str, container: Container = Depends(get_container)
) -> StreamingResponse:
    session = _find_session(container, session_id)
    if session.status not in (SessionStatus.COMPLETED, SessionStatus.FAILED):
        raise HTTPException(
            status.HTTP_425_TOO_EARLY,
            "Bundle chỉ có sau khi phiên hoàn tất.",
        )
    repo = container.artifact_repo()
    arts = repo.list_for_session(session.source_id, session_id)
    if not arts:
        raise HTTPException(404, "Không có artifact nào để bundle.")

    bundle_root = f"{session.source_id}_{session_id}"
    stream = _zipstream(arts, bundle_root)
    headers = {
        "Content-Disposition": f'attachment; filename="{bundle_root}_bundle.zip"',
    }
    return StreamingResponse(stream, media_type="application/zip", headers=headers)


def _zipstream(artifacts: Iterable[Artifact], root_name: str):
    """Generate ZIP bytes lazily — each file added to archive is yielded as bytes
    so server không buffer toàn bộ vào RAM. Sử dụng ``zipstream-ng``.
    """
    try:
        from zipstream import ZipStream  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(500, "zipstream-ng chưa cài; bundle endpoint không khả dụng.") from exc

    zs = ZipStream(sized=False)
    for art in artifacts:
        if art.kind == "roi":
            arcname = f"{root_name}/roi.json"
        elif art.kind == "frame":
            arcname = f"{root_name}/frames/{art.name}"
        else:
            arcname = f"{root_name}/{art.name}"
        zs.add_path(str(art.path), arcname=arcname)

    yield from zs


def _require_artifact(
    session: AnalysisSession, art: Artifact | None, kind: ArtifactKind
) -> None:
    if art is not None:
        return
    if session.status in (SessionStatus.PENDING, SessionStatus.RUNNING):
        raise HTTPException(
            status.HTTP_425_TOO_EARLY,
            f"Artifact '{kind}' chưa sẵn sàng — phiên đang chạy.",
        )
    raise HTTPException(404, f"Artifact '{kind}' không có cho session '{session.id}'.")
