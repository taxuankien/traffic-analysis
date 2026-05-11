"""System endpoints: health, monitor, models list."""
from __future__ import annotations

import logging
import shutil
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.adapters.input.web.deps import get_container
from src.adapters.input.web.schemas.inference_config import ModelFileInfo
from src.adapters.input.web.schemas.system import (
    GPUInfo,
    HealthResponse,
    SystemMonitorResponse,
)
from src.bootstrap.container import Container
from src.bootstrap.paths import DEFAULT_MODELS_DIR

logger = logging.getLogger(__name__)

# ── Known YOLO model catalog (name → approx size in MB) ─────────────
# ultralytics auto-downloads these when instantiated: YOLO("yolo11n.pt")
YOLO_CATALOG: list[dict] = [
    # YOLOv11 family
    {"name": "yolo11n.pt", "family": "YOLOv11", "variant": "Nano",   "size_mb": 5.4},
    {"name": "yolo11s.pt", "family": "YOLOv11", "variant": "Small",  "size_mb": 18.4},
    {"name": "yolo11m.pt", "family": "YOLOv11", "variant": "Medium", "size_mb": 38.8},
    {"name": "yolo11l.pt", "family": "YOLOv11", "variant": "Large",  "size_mb": 49.0},
    {"name": "yolo11x.pt", "family": "YOLOv11", "variant": "XLarge", "size_mb": 109.3},
    # YOLOv8 family
    {"name": "yolov8n.pt", "family": "YOLOv8", "variant": "Nano",   "size_mb": 6.2},
    {"name": "yolov8s.pt", "family": "YOLOv8", "variant": "Small",  "size_mb": 21.5},
    {"name": "yolov8m.pt", "family": "YOLOv8", "variant": "Medium", "size_mb": 49.7},
    {"name": "yolov8l.pt", "family": "YOLOv8", "variant": "Large",  "size_mb": 83.7},
    {"name": "yolov8x.pt", "family": "YOLOv8", "variant": "XLarge", "size_mb": 130.5},
]

# Track in-progress downloads
_download_lock = threading.Lock()
_downloading: dict[str, str] = {}  # model_name → status ("downloading" | "done" | "failed")

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/system/monitor", response_model=SystemMonitorResponse)
def system_monitor(container: Container = Depends(get_container)) -> SystemMonitorResponse:
    snap = container.system_monitor().snapshot()
    return SystemMonitorResponse(
        cpu_percent=snap.cpu_percent,
        ram_percent=snap.ram_percent,
        gpu=[
            GPUInfo(
                name=g.name,
                util_percent=g.utilization_percent,
                mem_used_mb=g.memory_used_mb,
                mem_total_mb=g.memory_total_mb,
            )
            for g in snap.gpus
        ],
    )


@router.get("/system/models", response_model=list[ModelFileInfo])
def list_models() -> list[ModelFileInfo]:
    """List ``*.pt`` files in ``TRAFFIC_MODELS_DIR`` for UI weights picker."""
    models_dir = DEFAULT_MODELS_DIR
    if not models_dir.is_dir():
        return []
    out: list[ModelFileInfo] = []
    for f in sorted(models_dir.glob("*.pt")):
        try:
            size = f.stat().st_size
        except OSError:
            continue
        out.append(
            ModelFileInfo(
                name=f.name,
                path=str(f),
                size_mb=round(size / (1024 * 1024), 2),
            )
        )
    return out


# ── Model catalog & download ─────────────────────────────────────────

class CatalogModel(BaseModel):
    name: str
    family: str
    variant: str
    size_mb: float
    downloaded: bool = False


class DownloadRequest(BaseModel):
    model_name: str = Field(..., description="e.g. 'yolo11n.pt'")


class DownloadResponse(BaseModel):
    model_name: str
    status: str  # "downloading" | "done" | "already_exists" | "failed"
    message: str


@router.get("/system/models/catalog", response_model=list[CatalogModel])
def list_catalog() -> list[CatalogModel]:
    """Return known YOLO models with download status."""
    local_names = set()
    if DEFAULT_MODELS_DIR.is_dir():
        local_names = {f.name for f in DEFAULT_MODELS_DIR.glob("*.pt")}
    return [
        CatalogModel(
            name=m["name"],
            family=m["family"],
            variant=m["variant"],
            size_mb=m["size_mb"],
            downloaded=m["name"] in local_names,
        )
        for m in YOLO_CATALOG
    ]


@router.post("/system/models/download", response_model=DownloadResponse)
def download_model(body: DownloadRequest) -> DownloadResponse:
    """Download a YOLO model via ultralytics auto-download.

    The model is downloaded to the default ultralytics cache then copied
    to ``models/`` so it appears in the local models list.
    """
    model_name = body.model_name.strip()
    if not model_name.endswith(".pt"):
        raise HTTPException(400, "Model name must end with .pt")

    target = DEFAULT_MODELS_DIR / model_name
    if target.is_file():
        return DownloadResponse(
            model_name=model_name,
            status="already_exists",
            message=f"{model_name} đã có sẵn ({target.stat().st_size / 1024 / 1024:.1f} MB).",
        )

    with _download_lock:
        if _downloading.get(model_name) == "downloading":
            return DownloadResponse(
                model_name=model_name,
                status="downloading",
                message=f"{model_name} đang được tải...",
            )
        _downloading[model_name] = "downloading"

    # Run download synchronously (ultralytics handles progress internally)
    try:
        from ultralytics import YOLO

        logger.info("Downloading model %s via ultralytics...", model_name)
        DEFAULT_MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # ultralytics YOLO() auto-downloads to its cache if not found locally.
        # We instantiate with just the name so it downloads, then copy the
        # resolved weights file to our models/ directory.
        model = YOLO(model_name)
        src_path = Path(model.ckpt_path)

        if src_path.resolve() != target.resolve():
            shutil.copy2(str(src_path), str(target))
            logger.info("Copied %s → %s", src_path, target)

        with _download_lock:
            _downloading[model_name] = "done"

        size_mb = target.stat().st_size / 1024 / 1024
        return DownloadResponse(
            model_name=model_name,
            status="done",
            message=f"Đã tải {model_name} thành công ({size_mb:.1f} MB).",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to download %s: %s", model_name, exc)
        with _download_lock:
            _downloading[model_name] = "failed"
        raise HTTPException(500, f"Tải model thất bại: {exc}") from exc
