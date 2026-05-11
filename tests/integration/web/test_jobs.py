"""Phase 3 tests — JobManager state machine + summary generation.

Không gọi YOLO/video reader thật; thay AnalysisService bằng fake để cô lập
JobManager logic (thread pool, cancel event, broadcast, summary gen).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from src.adapters.input.web.jobs import JobManager
from src.application.ports.input.analysis_port import AnalysisProgress
from src.application.services.analysis_service import CancelledError
from src.bootstrap.container import Container
from src.bootstrap.inference_config import InferenceConfig
from src.domain.entities.analysis_session import AnalysisSession, SessionStatus
from src.domain.entities.video_source import VideoSource, VideoSourceKind
from src.domain.value_objects.analysis_interval import AnalysisInterval


class FakeAnalysisService:
    """Stand-in AnalysisService dùng cho test JobManager."""

    def __init__(
        self,
        session_repo,
        interval_repo,
        *,
        intervals_to_emit: int = 2,
        sleep_per_step: float = 0.01,
        fail: bool = False,
    ) -> None:
        self._sessions = session_repo
        self._intervals = interval_repo
        self._intervals_to_emit = intervals_to_emit
        self._sleep = sleep_per_step
        self._fail = fail

    def start_session(self, source_id: str, interval_seconds: float | None = None) -> AnalysisSession:
        sess = AnalysisSession(
            id=f"sess_{source_id}_{int(time.time() * 1000) % 1_000_000:06d}",
            source_id=source_id,
            interval_seconds=interval_seconds or 30.0,
        )
        self._sessions.save(sess)
        return sess

    def run_session(
        self,
        session_id,
        progress_cb=None,
        annotated_output_path=None,
        interval_cb=None,
        cancel_event=None,
    ):
        session = self._lookup(session_id)
        session.mark_started()
        self._sessions.save(session)
        try:
            for i in range(self._intervals_to_emit):
                if cancel_event is not None and cancel_event.is_set():
                    raise CancelledError("cancel")
                time.sleep(self._sleep)
                if self._fail and i == 0:
                    raise RuntimeError("simulated failure")
                interval = AnalysisInterval(
                    timestamp=datetime.now(),
                    duration_seconds=30.0,
                    vehicle_counts={"car": i + 1},
                )
                self._intervals.append(session.source_id, session.id, interval)
                if interval_cb:
                    interval_cb(interval)
                if progress_cb:
                    progress_cb(
                        AnalysisProgress(
                            session_id=session.id,
                            current_frame=(i + 1) * 30,
                            total_frames=self._intervals_to_emit * 30,
                            elapsed_seconds=0.0,
                            intervals_completed=i + 1,
                        )
                    )
            session.mark_completed()
            self._sessions.save(session)
            return session
        except CancelledError:
            session.mark_cancelled()
            self._sessions.save(session)
            raise
        except Exception as exc:
            session.mark_failed(str(exc))
            self._sessions.save(session)
            raise

    def _lookup(self, session_id):
        for s in self._sessions._load(  # noqa: SLF001 — test reach into JSONSessionRepository
            "src_test"
        ):
            if s["id"] == session_id:
                return AnalysisSession.from_dict(s)
        raise LookupError(session_id)


@pytest.fixture
def container_with_source(tmp_path):
    container = Container(
        data_dir=tmp_path / "data",
        inference_config=InferenceConfig(),
    )
    # Seed source + roi config so start_session won't reject.
    source = VideoSource(id="src_test", name="Test", path="/tmp/fake.mp4", kind=VideoSourceKind.FILE)
    container.source_repo.save(source)
    # Minimal ROI: empty config OK for test.
    from src.domain.entities.roi_config import ROIConfig

    container.roi_repo.save(ROIConfig(source_id="src_test"))
    return container


def _patch_analysis_service(container, fake):
    container.analysis_service = lambda *args, **kwargs: fake


def test_job_runs_to_completion_and_writes_summary(container_with_source, tmp_path):
    fake = FakeAnalysisService(container_with_source.session_repo, container_with_source.interval_repo)
    _patch_analysis_service(container_with_source, fake)
    jobs = JobManager(container_with_source, max_workers=1)
    try:
        session = jobs.start("src_test", interval_seconds=30.0)
        # Wait for completion.
        for _ in range(200):
            updated = container_with_source.session_repo.get("src_test", session.id)
            if updated.status == SessionStatus.COMPLETED:
                break
            time.sleep(0.02)
        assert updated.status == SessionStatus.COMPLETED
        # Wait for summary.json file to be written by worker (post-run in _run).
        summary_path = (
            container_with_source.data_dir
            / "results"
            / "src_test"
            / session.id
            / "summary.json"
        )
        for _ in range(100):
            if summary_path.is_file():
                break
            time.sleep(0.02)
        assert summary_path.is_file()
        body = json.loads(summary_path.read_text(encoding="utf-8"))
        assert body["interval_count"] == 2
        # CSV reader fills 0 for absent classes; only meaningful invariant is car total.
        assert body["totals"].get("car") == 3  # 1 + 2
    finally:
        jobs.shutdown(wait=True)


def test_job_cancel_marks_session_cancelled(container_with_source):
    fake = FakeAnalysisService(
        container_with_source.session_repo,
        container_with_source.interval_repo,
        intervals_to_emit=20,
        sleep_per_step=0.05,
    )
    _patch_analysis_service(container_with_source, fake)
    jobs = JobManager(container_with_source, max_workers=1)
    try:
        session = jobs.start("src_test", interval_seconds=30.0)
        time.sleep(0.05)
        ok = jobs.cancel(session.id)
        assert ok is True
        for _ in range(200):
            updated = container_with_source.session_repo.get("src_test", session.id)
            if updated.status == SessionStatus.CANCELLED:
                break
            time.sleep(0.02)
        assert updated.status == SessionStatus.CANCELLED
    finally:
        jobs.shutdown(wait=True)


def test_job_failure_marks_session_failed(container_with_source):
    fake = FakeAnalysisService(
        container_with_source.session_repo,
        container_with_source.interval_repo,
        fail=True,
    )
    _patch_analysis_service(container_with_source, fake)
    jobs = JobManager(container_with_source, max_workers=1)
    try:
        session = jobs.start("src_test", interval_seconds=30.0)
        for _ in range(200):
            updated = container_with_source.session_repo.get("src_test", session.id)
            if updated.status == SessionStatus.FAILED:
                break
            time.sleep(0.02)
        assert updated.status == SessionStatus.FAILED
        assert "simulated failure" in (updated.error_message or "")
    finally:
        jobs.shutdown(wait=True)


def test_job_pool_full_rejects_with_runtime_error(container_with_source):
    fake = FakeAnalysisService(
        container_with_source.session_repo,
        container_with_source.interval_repo,
        intervals_to_emit=10,
        sleep_per_step=0.05,
    )
    _patch_analysis_service(container_with_source, fake)
    jobs = JobManager(container_with_source, max_workers=1)
    try:
        first = jobs.start("src_test", interval_seconds=30.0)
        with pytest.raises(RuntimeError):
            jobs.start("src_test", interval_seconds=30.0)
        jobs.cancel(first.id)
        # Wait so first finishes.
        time.sleep(0.2)
    finally:
        jobs.shutdown(wait=True)


def test_progress_state_updates(container_with_source):
    fake = FakeAnalysisService(
        container_with_source.session_repo,
        container_with_source.interval_repo,
        intervals_to_emit=3,
    )
    _patch_analysis_service(container_with_source, fake)
    jobs = JobManager(container_with_source, max_workers=1)
    try:
        session = jobs.start("src_test", interval_seconds=30.0)
        # Wait completion then verify final progress was captured.
        for _ in range(200):
            updated = container_with_source.session_repo.get("src_test", session.id)
            if updated.status == SessionStatus.COMPLETED:
                break
            time.sleep(0.02)
        progress = jobs.progress(session.id)
        assert progress is not None
        assert progress.current_interval == 3
    finally:
        jobs.shutdown(wait=True)
