"""CRUD VideoSource + multipart upload."""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from src.adapters.input.web.deps import get_container
from src.adapters.input.web.schemas.source import (
    VideoSourceMetadata,
    VideoSourceResponse,
)
from src.bootstrap.container import Container
from src.domain.entities.video_source import VideoSource

router = APIRouter(prefix="/sources", tags=["sources"])
logger = logging.getLogger(__name__)

_ALLOWED_EXT = {".mp4", ".avi", ".mov", ".mkv"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _to_response(source: VideoSource) -> VideoSourceResponse:
    return VideoSourceResponse(
        id=source.id,
        name=source.name,
        path=source.path,
        kind=source.kind.value,
        created_at=source.created_at,
        metadata=VideoSourceMetadata(
            fps=source.fps,
            total_frames=source.total_frames,
            width=source.width,
            height=source.height,
        ),
    )


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME.sub("_", name).strip("._")
    return cleaned or "video"


@router.get("", response_model=list[VideoSourceResponse])
def list_sources(container: Container = Depends(get_container)) -> list[VideoSourceResponse]:
    return [_to_response(s) for s in container.data_management_service().list_sources()]


@router.get("/{source_id}", response_model=VideoSourceResponse)
def get_source(
    source_id: str, container: Container = Depends(get_container)
) -> VideoSourceResponse:
    source = container.data_management_service().get_source(source_id)
    return _to_response(source)


@router.post(
    "",
    response_model=VideoSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_source(
    name: str = Form(..., min_length=1, max_length=200),
    file: UploadFile = File(...),
    container: Container = Depends(get_container),
) -> VideoSourceResponse:
    """Upload video bytes vào ``data/uploads/`` và đăng ký nguồn.

    Stream file từ multipart vào đích — không buffer toàn bộ vào RAM.
    """
    filename = file.filename or "upload.mp4"
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng không hỗ trợ: {ext}. Cho phép: {sorted(_ALLOWED_EXT)}",
        )

    uploads_dir = container.data_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Allocate source_id-style temp path; rename after persist for clarity.
    import uuid

    temp_id = uuid.uuid4().hex[:10]
    safe_name = _safe_filename(filename)
    target = uploads_dir / f"upload_{temp_id}_{safe_name}"

    try:
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)
    except Exception as exc:  # noqa: BLE001
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu file: {exc}") from exc
    finally:
        file.file.close()

    if target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="File upload rỗng.")

    service = container.data_management_service()
    try:
        source = service.add_source_from_uploaded_path(name, target)
    except Exception:
        target.unlink(missing_ok=True)
        raise

    # Rename to canonical {source_id}_{filename} so admins can locate easily.
    canonical = uploads_dir / f"{source.id}_{safe_name}"
    if canonical != target:
        try:
            target.rename(canonical)
            source.path = str(canonical)
            container.source_repo.save(source)
        except OSError:
            logger.warning("Không thể rename %s → %s; giữ tên upload tạm.", target, canonical)

    # Best-effort metadata fill (not fatal if reader fails on a non-video upload).
    try:
        meta = container.video_reader.get_metadata(source.path)
        source.fps = meta.fps
        source.total_frames = meta.total_frames
        source.width = meta.width
        source.height = meta.height
        container.source_repo.save(source)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không đọc được metadata cho %s: %s", source.path, exc)

    return _to_response(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: str,
    purge: bool = False,
    container: Container = Depends(get_container),
) -> None:
    """Xoá entry source. Với ``?purge=true``, xoá luôn file video + results folder.

    Mặc định KHÔNG purge để tránh mất dữ liệu vô ý.
    """
    service = container.data_management_service()
    source = service.get_source(source_id)
    service.delete_source(source_id)

    if purge:
        try:
            video_path = Path(source.path)
            if video_path.is_file() and _is_inside(video_path, container.data_dir):
                video_path.unlink()
        except OSError as exc:
            logger.warning("Không xoá được %s: %s", source.path, exc)
        results_dir = container.data_dir / "results" / source_id
        if results_dir.is_dir():
            shutil.rmtree(results_dir, ignore_errors=True)


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
