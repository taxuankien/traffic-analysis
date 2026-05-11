"""Tests cho POST /api/sessions/{id}/render-video — render annotated.mp4 sau khi xong.

Mock VisualizationService.render_full_video để không phụ thuộc YOLO/video reader.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def completed_session(client, container):
    source_id = "src_render"
    session_id = "sess_render"
    sources_dir = container.data_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.joinpath("sources.json").write_text(
        json.dumps(
            [
                {
                    "id": source_id,
                    "name": "Cam Render",
                    "path": "uploads/r.mp4",
                    "kind": "file",
                    "created_at": datetime.now().isoformat(),
                }
            ]
        ),
        encoding="utf-8",
    )
    (container.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (container.data_dir / "uploads" / "r.mp4").write_bytes(b"\0" * 16)

    results_dir = container.data_dir / "results" / source_id
    results_dir.mkdir(parents=True, exist_ok=True)
    results_dir.joinpath("sessions.json").write_text(
        json.dumps(
            [
                {
                    "id": session_id,
                    "source_id": source_id,
                    "status": "completed",
                    "interval_seconds": 30.0,
                    "started_at": datetime.now().isoformat(),
                    "finished_at": datetime.now().isoformat(),
                    "error_message": None,
                    "created_at": datetime.now().isoformat(),
                }
            ]
        ),
        encoding="utf-8",
    )
    return source_id, session_id


def test_render_video_endpoint_schedules_job(client, completed_session, container, monkeypatch):
    source_id, session_id = completed_session
    sess_dir = container.data_dir / "results" / source_id / session_id

    # Fake visualization service: write a dummy mp4 to target path synchronously.
    class _FakeViz:
        def render_full_video(self, sid, target_path, progress_cb=None):
            Path(target_path).parent.mkdir(parents=True, exist_ok=True)
            Path(target_path).write_bytes(b"\x00\x00\x00\x18ftypmp42")
            return target_path

    monkeypatch.setattr(container, "visualization_service", lambda *a, **k: _FakeViz())

    r = client.post(f"/api/sessions/{session_id}/render-video")
    assert r.status_code == 202
    body = r.json()
    assert body["session_id"] == session_id
    assert body["download_url"].endswith(f"/sessions/{session_id}/download/video")

    # Wait for render to finish (executor + sync fake → fast).
    target = sess_dir / "annotated.mp4"
    for _ in range(100):
        if target.is_file():
            break
        time.sleep(0.02)
    assert target.is_file()


def test_render_status_returns_done_after_completion(client, completed_session, container, monkeypatch):
    source_id, session_id = completed_session

    class _FakeViz:
        def render_full_video(self, sid, target_path, progress_cb=None):
            Path(target_path).parent.mkdir(parents=True, exist_ok=True)
            Path(target_path).write_bytes(b"x")
            return target_path

    monkeypatch.setattr(container, "visualization_service", lambda *a, **k: _FakeViz())

    client.post(f"/api/sessions/{session_id}/render-video")
    for _ in range(100):
        r = client.get(f"/api/sessions/{session_id}/render-video")
        if r.json()["status"] == "done":
            break
        time.sleep(0.02)
    assert r.json()["status"] == "done"
    assert r.json()["available"] is True


def test_render_rejected_for_running_session(client, container):
    """Session đang running → 409."""
    source_id = "src_run"
    session_id = "sess_run"
    sources_dir = container.data_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.joinpath("sources.json").write_text(
        json.dumps(
            [
                {
                    "id": source_id,
                    "name": "X",
                    "path": "uploads/x.mp4",
                    "kind": "file",
                    "created_at": datetime.now().isoformat(),
                }
            ]
        ),
        encoding="utf-8",
    )
    results_dir = container.data_dir / "results" / source_id
    results_dir.mkdir(parents=True, exist_ok=True)
    results_dir.joinpath("sessions.json").write_text(
        json.dumps(
            [
                {
                    "id": session_id,
                    "source_id": source_id,
                    "status": "running",
                    "interval_seconds": 30.0,
                    "started_at": datetime.now().isoformat(),
                    "finished_at": None,
                    "error_message": None,
                    "created_at": datetime.now().isoformat(),
                }
            ]
        ),
        encoding="utf-8",
    )

    r = client.post(f"/api/sessions/{session_id}/render-video")
    assert r.status_code == 409


def test_frame_download_rejects_path_traversal(client, completed_session):
    _, session_id = completed_session
    r = client.get(f"/api/sessions/{session_id}/frames/..%2F..%2Fetc%2Fpasswd")
    # FastAPI route doesn't match path traversal at URL level → 404 or 400
    assert r.status_code in (400, 404)


def test_frame_download_returns_file(client, container, completed_session):
    source_id, session_id = completed_session
    frames_dir = container.data_dir / "results" / source_id / session_id / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    (frames_dir / "frame_0001.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 16)

    r = client.get(f"/api/sessions/{session_id}/frames/frame_0001.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_frame_download_404_when_missing(client, completed_session):
    _, session_id = completed_session
    r = client.get(f"/api/sessions/{session_id}/frames/nonexistent.png")
    assert r.status_code == 404
