from __future__ import annotations

from io import BytesIO
from pathlib import Path


def test_list_sources_empty(client):
    r = client.get("/api/sources")
    assert r.status_code == 200
    assert r.json() == []


def test_upload_source_rejects_bad_extension(client):
    r = client.post(
        "/api/sources",
        data={"name": "bad"},
        files={"file": ("evil.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert "Định dạng" in r.json()["detail"] or "Không hỗ trợ" in r.json()["detail"]


def test_upload_source_writes_into_uploads_dir(client, container):
    fake_video = b"\0" * 1024  # not a real video; metadata extraction will fail gracefully
    r = client.post(
        "/api/sources",
        data={"name": "Cam 1"},
        files={"file": ("cam1.mp4", BytesIO(fake_video), "video/mp4")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Cam 1"
    assert body["id"].startswith("src_")

    uploads = container.data_dir / "uploads"
    files = list(uploads.glob("*.mp4"))
    assert len(files) == 1
    assert files[0].read_bytes() == fake_video


def test_get_source_404_when_missing(client):
    r = client.get("/api/sources/src_does_not_exist")
    assert r.status_code == 404


def test_delete_source_without_purge_keeps_file(client, container):
    fake_video = b"\0" * 256
    r = client.post(
        "/api/sources",
        data={"name": "Cam 2"},
        files={"file": ("cam2.mp4", BytesIO(fake_video), "video/mp4")},
    )
    sid = r.json()["id"]
    video_path = Path(r.json()["path"])
    assert video_path.is_file()

    r = client.delete(f"/api/sources/{sid}")
    assert r.status_code == 204
    assert video_path.is_file()  # not purged


def test_delete_source_with_purge_removes_file(client, container):
    fake_video = b"\0" * 256
    r = client.post(
        "/api/sources",
        data={"name": "Cam 3"},
        files={"file": ("cam3.mp4", BytesIO(fake_video), "video/mp4")},
    )
    sid = r.json()["id"]
    video_path = Path(r.json()["path"])

    r = client.delete(f"/api/sources/{sid}?purge=true")
    assert r.status_code == 204
    assert not video_path.exists()
