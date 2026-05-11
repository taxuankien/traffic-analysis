from __future__ import annotations

from io import BytesIO


def _add_source(client, name="Cam") -> str:
    r = client.post(
        "/api/sources",
        data={"name": name},
        files={"file": ("v.mp4", BytesIO(b"\0" * 64), "video/mp4")},
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_get_roi_returns_null_when_unset(client):
    sid = _add_source(client)
    r = client.get(f"/api/sources/{sid}/roi")
    assert r.status_code == 200
    assert r.json() is None


def test_put_roi_then_get_roi(client):
    sid = _add_source(client)
    payload = {
        "reference_frame_index": 5,
        "roi_polygons": [
            {"name": "lane", "points": [[0, 0], [100, 0], [100, 100], [0, 100]]}
        ],
        "counting_lines": [
            {"name": "in_line", "start": [10, 50], "end": [90, 50], "direction": "in"}
        ],
        "pixels_per_meter": 12.5,
    }
    r = client.put(f"/api/sources/{sid}/roi", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["pixels_per_meter"] == 12.5
    assert len(body["roi_polygons"]) == 1
    assert body["counting_lines"][0]["direction"] == "in"

    r2 = client.get(f"/api/sources/{sid}/roi")
    assert r2.status_code == 200
    assert r2.json()["reference_frame_index"] == 5


def test_put_roi_404_for_unknown_source(client):
    r = client.put(
        "/api/sources/src_does_not_exist/roi",
        json={
            "roi_polygons": [{"name": "x", "points": [[0, 0], [1, 0], [0, 1]]}],
            "counting_lines": [],
            "pixels_per_meter": 0,
        },
    )
    assert r.status_code == 404
