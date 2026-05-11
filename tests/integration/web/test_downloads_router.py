"""Phase 2: download endpoints (artifacts + per-kind + bundle ZIP).

Set up filesystem state directly (sources.json + roi.json + result.csv +
summary.json) thay vì chạy AnalysisService — Phase 3 mới có job thực sự.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from io import BytesIO

import pytest


@pytest.fixture
def session_with_artifacts(client, container):
    # Seed source.
    sources_dir = container.data_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    source_id = "src_test01"
    session_id = "sess_test01"
    sources_dir.joinpath("sources.json").write_text(
        json.dumps(
            [
                {
                    "id": source_id,
                    "name": "Test Cam",
                    "path": "uploads/test.mp4",
                    "kind": "file",
                    "created_at": datetime.now().isoformat(),
                }
            ]
        ),
        encoding="utf-8",
    )
    (container.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (container.data_dir / "uploads" / "test.mp4").write_bytes(b"\0" * 32)

    # ROI config (per-source).
    configs_dir = container.data_dir / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    roi_payload = {
        "source_id": source_id,
        "reference_frame_index": 0,
        "roi_polygons": [],
        "counting_lines": [],
        "pixels_per_meter": 0.0,
        "detection_roi": None,
        "created_at": datetime.now().isoformat(),
    }
    configs_dir.joinpath(f"{source_id}.json").write_text(
        json.dumps(roi_payload), encoding="utf-8"
    )

    # Session in completed state + artifacts.
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
    sess_dir = results_dir / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    (sess_dir / "result.csv").write_text("timestamp,duration_seconds\n", encoding="utf-8")
    (sess_dir / "summary.json").write_text(json.dumps({"total": 0}), encoding="utf-8")
    return source_id, session_id


def test_list_artifacts_includes_csv_summary_roi(client, session_with_artifacts):
    _, session_id = session_with_artifacts
    r = client.get(f"/api/sessions/{session_id}/artifacts")
    assert r.status_code == 200
    arts = r.json()
    kinds = {a["kind"] for a in arts}
    assert {"csv", "summary", "roi"} <= kinds
    assert "video" not in kinds  # render_video not enabled


def test_download_csv_returns_file(client, session_with_artifacts):
    _, session_id = session_with_artifacts
    r = client.get(f"/api/sessions/{session_id}/download/csv")
    assert r.status_code == 200
    assert "csv" in r.headers["content-type"]
    assert "attachment" in r.headers.get("content-disposition", "")


def test_download_summary_returns_json(client, session_with_artifacts):
    _, session_id = session_with_artifacts
    r = client.get(f"/api/sessions/{session_id}/download/summary")
    assert r.status_code == 200


def test_download_video_404_when_not_rendered(client, session_with_artifacts):
    _, session_id = session_with_artifacts
    r = client.get(f"/api/sessions/{session_id}/download/video")
    assert r.status_code == 404


def test_download_roi_returns_json(client, session_with_artifacts):
    source_id, _ = session_with_artifacts
    r = client.get(f"/api/sources/{source_id}/download/roi.json")
    assert r.status_code == 200


def test_download_bundle_zip_streams(client, session_with_artifacts):
    _, session_id = session_with_artifacts
    r = client.get(f"/api/sessions/{session_id}/download/bundle.zip")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    body = r.content
    z = zipfile.ZipFile(BytesIO(body))
    names = z.namelist()
    assert any(n.endswith("result.csv") for n in names)
    assert any(n.endswith("summary.json") for n in names)
    assert any(n.endswith("roi.json") for n in names)


def test_session_404_for_unknown(client):
    r = client.get("/api/sessions/sess_nope/artifacts")
    assert r.status_code == 404
