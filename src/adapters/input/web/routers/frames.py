"""Frame extraction + test detection (Luồng 1b qua web)."""
from __future__ import annotations

from io import BytesIO
from typing import Annotated

import cv2
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.adapters.input.web.deps import get_container
from src.bootstrap.container import Container

router = APIRouter(prefix="/sources/{source_id}", tags=["frames"])


def _resolve_index(
    container: Container, source_id: str, time: float | None, frame: int | None
) -> int:
    if (time is None) == (frame is None):
        raise HTTPException(400, "Phải truyền đúng một trong: time (giây) hoặc frame (index).")
    if frame is not None:
        if frame < 0:
            raise HTTPException(400, "frame >= 0")
        return frame
    assert time is not None
    if time < 0:
        raise HTTPException(400, "time >= 0")
    source = container.source_repo.get(source_id)
    meta = container.video_reader.get_metadata(source.path)
    if meta.fps <= 0:
        raise HTTPException(400, f"Video có fps không hợp lệ: {meta.fps}")
    idx = int(round(time * meta.fps))
    if meta.total_frames > 0:
        idx = min(idx, meta.total_frames - 1)
    return idx


@router.get("/frame")
def extract_frame(
    source_id: str,
    time: Annotated[float | None, Query(ge=0, description="Timestamp (giây)")] = None,
    frame: Annotated[int | None, Query(ge=0, description="Frame index (0-based)")] = None,
    container: Container = Depends(get_container),
) -> StreamingResponse:
    idx = _resolve_index(container, source_id, time, frame)
    image = container.frame_extraction_service().extract_frame(source_id, idx)
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise HTTPException(500, "Không encode được frame thành PNG")
    return StreamingResponse(
        BytesIO(buf.tobytes()),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )


class TestDetectRequest(BaseModel):
    time: float | None = Field(default=None, ge=0)
    frame: int | None = Field(default=None, ge=0)
    annotate: bool = True


class InferenceTimings(BaseModel):
    inference_ms: float | None = None
    annotation_ms: float | None = None
    total_ms: float | None = None
    fps_estimate: float | None = None
    device: str | None = None
    image_size: tuple[int, int] | None = None


class TestDetectResponse(BaseModel):
    frame_index: int
    detections: list[dict]
    summary: dict[str, int]
    annotated_url: str | None = None
    timings: InferenceTimings | None = None


@router.post("/test-detect", response_model=TestDetectResponse)
def test_detect(
    source_id: str,
    body: TestDetectRequest,
    container: Container = Depends(get_container),
) -> TestDetectResponse:
    idx = _resolve_index(container, source_id, body.time, body.frame)
    service = container.frame_extraction_service()
    result = service.run_test_detection(source_id, idx)

    annotated_url = None
    if body.annotate:
        # Save annotated frame under data/frames/test_<source>_<idx>.png
        frames_dir = container.data_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        fname = f"test_{source_id}_{idx:06d}.png"
        out_path = frames_dir / fname
        ok = cv2.imwrite(str(out_path), result.annotated_frame)
        if ok:
            annotated_url = f"/files/frames/{fname}"

    fps_est: float | None = None
    if result.inference_ms and result.inference_ms > 0:
        fps_est = round(1000.0 / result.inference_ms, 1)

    timings = InferenceTimings(
        inference_ms=result.inference_ms,
        annotation_ms=result.annotation_ms,
        total_ms=result.total_ms,
        fps_estimate=fps_est,
        device=result.device,
        image_size=result.image_size,
    )

    return TestDetectResponse(
        frame_index=idx,
        detections=result.detections,
        summary=result.counts_by_class,
        annotated_url=annotated_url,
        timings=timings,
    )


class SaveFrameRequest(BaseModel):
    time: float | None = Field(default=None, ge=0)
    frame: int | None = Field(default=None, ge=0)


class SaveFrameResponse(BaseModel):
    frame_index: int
    url: str


@router.post("/frame/save", response_model=SaveFrameResponse)
def save_frame(
    source_id: str,
    body: SaveFrameRequest,
    container: Container = Depends(get_container),
) -> SaveFrameResponse:
    idx = _resolve_index(container, source_id, body.time, body.frame)
    service = container.frame_extraction_service()
    image = service.extract_frame(source_id, idx)
    saved = service.save_frame(image, source_id, idx)
    rel = saved.relative_to(container.data_dir / "frames")
    return SaveFrameResponse(frame_index=idx, url=f"/files/frames/{rel.as_posix()}")
