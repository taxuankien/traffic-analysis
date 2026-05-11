"""Background job manager cho phiên phân tích batch.

Mỗi job chạy trong 1 thread của ``ThreadPoolExecutor``. Limit qua env
``TRAFFIC_MAX_JOBS`` (default 1 — phân tích nặng GPU). Khi pool full,
``start()`` raise ``RuntimeError`` → router trả 409.

Trạng thái job giữ in-memory + persist trạng thái cuối qua
``SessionRepository``. Restart server → mọi job đang chạy bị "mất"; trạng
thái trong session repo có thể vẫn là ``running`` — Phase 3 đánh dấu
``failed`` ở startup hook (tương lai). MVP: chấp nhận stale state.

Threading model:
    - Tạo ``threading.Event`` per session để cancel.
    - Progress qua callback đẩy vào in-memory queue per session; WS endpoint
      đọc queue.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from src.adapters.input.web.schemas.analysis import SessionProgress
from src.adapters.input.web.schemas.artifact import SessionSummary
from src.application.ports.input.analysis_port import AnalysisProgress
from src.bootstrap.container import Container
from src.domain.entities.analysis_session import AnalysisSession, SessionStatus
from src.domain.exceptions import ROIConfigNotFoundError
from src.domain.value_objects.analysis_interval import AnalysisInterval

logger = logging.getLogger(__name__)


@dataclass
class JobState:
    session: AnalysisSession
    cancel_event: threading.Event = field(default_factory=threading.Event)
    progress: SessionProgress | None = None
    last_event: dict | None = None  # last broadcast event for late subscribers
    intervals_completed: int = 0
    render_video: bool = False
    artifacts_ready: dict[str, str] = field(default_factory=dict)  # kind → URL
    future: Future | None = None
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    loop: asyncio.AbstractEventLoop | None = None  # main loop for thread-safe enqueue


class JobManager:
    """Owns a thread pool and per-session state. Single instance per app."""

    def __init__(self, container: Container, max_workers: int = 1) -> None:
        self._container = container
        self._max = max(1, int(max_workers))
        self._executor = ThreadPoolExecutor(max_workers=self._max, thread_name_prefix="analysis-job")
        self._jobs: dict[str, JobState] = {}
        self._render_jobs: dict[str, Future] = {}
        self._lock = threading.Lock()

    # --- public API ----------------------------------------------------------

    def start(
        self, source_id: str, interval_seconds: float, render_video: bool = False
    ) -> AnalysisSession:
        with self._lock:
            running = sum(
                1
                for j in self._jobs.values()
                if j.session.status in (SessionStatus.PENDING, SessionStatus.RUNNING)
            )
            if running >= self._max:
                raise RuntimeError(
                    f"Đã đạt giới hạn {self._max} phiên đồng thời. Huỷ phiên đang chạy hoặc tăng TRAFFIC_MAX_JOBS."
                )
            service = self._container.analysis_service()
            try:
                session = service.start_session(source_id, interval_seconds=interval_seconds)
            except ROIConfigNotFoundError:
                raise
            state = JobState(
                session=session,
                render_video=render_video,
                loop=_running_loop_or_none(),
            )
            self._jobs[session.id] = state
            state.future = self._executor.submit(self._run, session.id)
            return session

    def cancel(self, session_id: str) -> bool:
        state = self._jobs.get(session_id)
        if state is None:
            return False
        if state.session.status in (
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        ):
            return False
        state.cancel_event.set()
        return True

    def progress(self, session_id: str) -> SessionProgress | None:
        state = self._jobs.get(session_id)
        return state.progress if state else None

    def subscribe(self, session_id: str) -> tuple[asyncio.Queue, dict | None]:
        """Đăng ký subscriber cho WS broadcasts; trả về queue + last event để replay."""
        state = self._jobs.get(session_id)
        if state is None:
            raise KeyError(session_id)
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        state.subscribers.append(queue)
        if state.loop is None:
            try:
                state.loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        return queue, state.last_event

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        state = self._jobs.get(session_id)
        if state is None:
            return
        try:
            state.subscribers.remove(queue)
        except ValueError:
            pass

    def shutdown(self, wait: bool = False) -> None:
        for state in self._jobs.values():
            state.cancel_event.set()
        self._executor.shutdown(wait=wait)

    def start_render(self, source_id: str, session_id: str) -> str:
        """Schedule post-hoc render annotated.mp4 for a completed session.

        Trả về đường dẫn tương lai của file. Render chạy trên cùng executor
        nên dùng chung pool size với analysis — tránh GPU contention.

        Raises:
            RuntimeError: pool full hoặc session đang ở trạng thái không hợp lệ
            FileNotFoundError: session không tồn tại trên storage
        """
        session = self._container.session_repo.get(source_id, session_id)
        if session.status not in (SessionStatus.COMPLETED, SessionStatus.CANCELLED, SessionStatus.FAILED):
            raise RuntimeError(
                f"Chỉ render được khi session đã kết thúc. Trạng thái hiện tại: {session.status.value}."
            )

        sess_dir = self._container.data_dir / "results" / source_id / session_id
        sess_dir.mkdir(parents=True, exist_ok=True)
        target = sess_dir / "annotated.mp4"

        with self._lock:
            existing = self._render_jobs.get(session_id)
            if existing is not None and not existing.done():
                # Already rendering — no-op, return target path.
                return str(target)
            self._render_jobs[session_id] = self._executor.submit(
                self._do_render, source_id, session_id, str(target)
            )
        return str(target)

    def render_status(self, session_id: str) -> str:
        """Trả 'idle' | 'running' | 'done' cho render job."""
        fut = self._render_jobs.get(session_id)
        if fut is None:
            return "idle"
        if fut.done():
            return "done"
        return "running"

    def _do_render(self, source_id: str, session_id: str, target: str) -> None:
        try:
            viz = self._container.visualization_service()
            viz.render_full_video(source_id, target_path=target)
            state = self._jobs.get(session_id)
            url = f"/api/sessions/{session_id}/download/video"
            if state is not None:
                state.artifacts_ready["video"] = url
                self._broadcast(
                    state,
                    {"type": "artifact_ready", "kind": "video", "url": url},
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Render failed for session=%s: %s", session_id, exc)
            state = self._jobs.get(session_id)
            if state is not None:
                self._broadcast(
                    state,
                    {"type": "render_failed", "session_id": session_id, "error": str(exc)},
                )

    # --- internals -----------------------------------------------------------

    def _run(self, session_id: str) -> None:
        state = self._jobs[session_id]
        service = self._container.analysis_service()

        # Capture interval_seconds-derived total via metadata for progress.
        try:
            source = self._container.source_repo.get(state.session.source_id)
            meta = self._container.video_reader.get_metadata(source.path)
            total_frames = meta.total_frames or 0
        except Exception:
            total_frames = 0

        def _on_progress(p: AnalysisProgress) -> None:
            sp = SessionProgress(
                processed_frames=p.current_frame,
                total_frames=p.total_frames or total_frames,
                current_interval=p.intervals_completed,
            )
            state.progress = sp
            state.intervals_completed = p.intervals_completed
            self._broadcast(
                state,
                {
                    "type": "progress",
                    "processed_frames": sp.processed_frames,
                    "total_frames": sp.total_frames,
                    "current_interval": sp.current_interval,
                },
            )

        def _on_interval(interval: AnalysisInterval) -> None:
            self._broadcast(
                state,
                {
                    "type": "interval",
                    "data": {
                        "timestamp": interval.timestamp.isoformat(),
                        "vehicle_counts": dict(interval.vehicle_counts),
                        "occupancy_ratio": interval.occupancy_ratio,
                        "avg_speed_kmh": interval.avg_speed_kmh,
                        "queue_length": interval.queue_length,
                    },
                },
            )

        annotated_path: str | None = None
        if state.render_video:
            sess_dir = self._container.data_dir / "results" / state.session.source_id / state.session.id
            sess_dir.mkdir(parents=True, exist_ok=True)
            annotated_path = str(sess_dir / "annotated.mp4")

        try:
            service.run_session(
                session_id=session_id,
                progress_cb=_on_progress,
                annotated_output_path=annotated_path,
                interval_cb=_on_interval,
                cancel_event=state.cancel_event,
            )
        except Exception as exc:  # noqa: BLE001
            # Status đã được service set sang failed/cancelled.
            updated = self._reload_session(state)
            if updated.status == SessionStatus.CANCELLED:
                self._broadcast(state, {"type": "cancelled", "session_id": session_id})
            else:
                self._broadcast(
                    state,
                    {"type": "failed", "session_id": session_id, "error": str(exc)},
                )
            return

        updated = self._reload_session(state)
        # Generate summary.json after successful completion.
        summary = _build_summary(self._container, updated)
        sess_dir = self._container.data_dir / "results" / updated.source_id / updated.id
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "summary.json").write_text(
            json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        state.artifacts_ready["summary"] = (
            f"/api/sessions/{updated.id}/download/summary"
        )
        state.artifacts_ready["csv"] = f"/api/sessions/{updated.id}/download/csv"
        if annotated_path and Path(annotated_path).is_file():
            state.artifacts_ready["video"] = (
                f"/api/sessions/{updated.id}/download/video"
            )

        self._broadcast(state, {"type": "completed", "session_id": session_id})
        for kind, url in state.artifacts_ready.items():
            self._broadcast(
                state, {"type": "artifact_ready", "kind": kind, "url": url}
            )

    def _reload_session(self, state: JobState) -> AnalysisSession:
        try:
            updated = self._container.session_repo.get(
                state.session.source_id, state.session.id
            )
            state.session = updated
            return updated
        except Exception:
            return state.session

    def _broadcast(self, state: JobState, event: dict) -> None:
        state.last_event = event
        loop = state.loop
        if loop is None:
            return
        for q in list(state.subscribers):
            try:
                loop.call_soon_threadsafe(_safe_put, q, event)
            except RuntimeError:
                # Loop closed
                continue


def _safe_put(queue: asyncio.Queue, event: dict) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        # Drop oldest to keep latest events flowing for slow clients.
        try:
            queue.get_nowait()
            queue.put_nowait(event)
        except Exception:  # noqa: BLE001
            pass


def _running_loop_or_none() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _build_summary(container: Container, session: AnalysisSession) -> SessionSummary:
    intervals = container.interval_repo.list(session.source_id, session.id)
    totals: dict[str, int] = {}
    occ_sum = 0.0
    speed_sum = 0.0
    for interval in intervals:
        for k, v in interval.vehicle_counts.items():
            totals[k] = totals.get(k, 0) + int(v)
        occ_sum += interval.occupancy_ratio
        speed_sum += interval.avg_speed_kmh

    n = max(1, len(intervals))
    duration = sum(i.duration_seconds for i in intervals)
    return SessionSummary(
        session_id=session.id,
        source_id=session.source_id,
        started_at=session.started_at,
        completed_at=session.finished_at,
        duration_seconds=float(duration),
        interval_count=len(intervals),
        interval_seconds=float(session.interval_seconds),
        totals=totals,
        avg_occupancy_ratio=round(occ_sum / n, 4),
        avg_speed_kmh=round(speed_sum / n, 2),
    )
