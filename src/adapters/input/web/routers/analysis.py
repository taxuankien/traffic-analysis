"""Analysis sessions: start (async), list, get, cancel, intervals.

Heavy lifting (worker pool, WS progress) lives in Phase 3 (``jobs.py`` +
``ws.py``). This router exposes the HTTP surface and delegates to
``app.state.jobs`` for start/cancel/state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.adapters.input.web.deps import get_container
from src.adapters.input.web.schemas.analysis import (
    AnalysisSessionResponse,
    IntervalResponse,
    SessionProgress,
    StartSessionRequest,
)
from src.bootstrap.container import Container
from src.domain.entities.analysis_session import AnalysisSession
from src.domain.exceptions import (
    AnalysisSessionNotFoundError,
    ROIConfigNotFoundError,
)
from src.domain.value_objects.analysis_interval import AnalysisInterval

router = APIRouter(tags=["analysis"])


def _session_to_response(
    session: AnalysisSession, progress: SessionProgress | None
) -> AnalysisSessionResponse:
    return AnalysisSessionResponse(
        id=session.id,
        source_id=session.source_id,
        status=session.status.value,
        interval_seconds=session.interval_seconds,
        progress=progress,
        started_at=session.started_at,
        finished_at=session.finished_at,
        error_message=session.error_message,
        created_at=session.created_at,
    )


def _interval_to_response(interval: AnalysisInterval) -> IntervalResponse:
    return IntervalResponse(
        timestamp=interval.timestamp,
        duration_seconds=interval.duration_seconds,
        vehicle_counts=dict(interval.vehicle_counts),
        counts_in=dict(interval.counts_in),
        counts_out=dict(interval.counts_out),
        occupancy_ratio=interval.occupancy_ratio,
        avg_speed_kmh=interval.avg_speed_kmh,
        queue_length=interval.queue_length,
    )


@router.post(
    "/sources/{source_id}/sessions",
    response_model=AnalysisSessionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_session(
    source_id: str,
    body: StartSessionRequest,
    request: Request,
    container: Container = Depends(get_container),
) -> AnalysisSessionResponse:
    container.source_repo.get(source_id)  # 404 nếu source không có
    if not container.roi_repo.exists(source_id):
        raise HTTPException(
            status_code=400,
            detail=f"Cần cấu hình ROI cho source '{source_id}' trước khi phân tích.",
        )

    jobs = getattr(request.app.state, "jobs", None)
    if jobs is None:
        raise HTTPException(503, "JobManager chưa khởi động.")

    try:
        session = jobs.start(
            source_id=source_id,
            interval_seconds=body.interval_seconds,
            render_video=body.render_video,
        )
    except ROIConfigNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        # Pool full / max_jobs reached
        raise HTTPException(409, str(exc)) from exc

    return _session_to_response(session, progress=None)


@router.get(
    "/sources/{source_id}/sessions",
    response_model=list[AnalysisSessionResponse],
)
def list_sessions(
    source_id: str, request: Request, container: Container = Depends(get_container)
) -> list[AnalysisSessionResponse]:
    container.source_repo.get(source_id)
    sessions = container.session_repo.list_for_source(source_id)
    jobs = getattr(request.app.state, "jobs", None)
    out: list[AnalysisSessionResponse] = []
    for s in sessions:
        progress = jobs.progress(s.id) if jobs else None
        out.append(_session_to_response(s, progress))
    return out


@router.get(
    "/sessions/{session_id}",
    response_model=AnalysisSessionResponse,
)
def get_session(
    session_id: str, request: Request, container: Container = Depends(get_container)
) -> AnalysisSessionResponse:
    session = _find_session(container, session_id)
    jobs = getattr(request.app.state, "jobs", None)
    progress = jobs.progress(session_id) if jobs else None
    return _session_to_response(session, progress)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_session(session_id: str, request: Request) -> None:
    jobs = getattr(request.app.state, "jobs", None)
    if jobs is None:
        raise HTTPException(503, "JobManager chưa khởi động.")
    if not jobs.cancel(session_id):
        raise HTTPException(404, f"Session '{session_id}' không đang chạy.")


@router.get(
    "/sessions/{session_id}/intervals",
    response_model=list[IntervalResponse],
)
def list_intervals(
    session_id: str,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    container: Container = Depends(get_container),
) -> list[IntervalResponse]:
    session = _find_session(container, session_id)
    intervals = container.interval_repo.list(
        session.source_id, session_id, start=start, end=end
    )
    return [_interval_to_response(i) for i in intervals]


def _find_session(container: Container, session_id: str) -> AnalysisSession:
    for src in container.source_repo.list_all():
        try:
            return container.session_repo.get(src.id, session_id)
        except AnalysisSessionNotFoundError:
            continue
    raise AnalysisSessionNotFoundError(f"Session '{session_id}' không tìm thấy.")
