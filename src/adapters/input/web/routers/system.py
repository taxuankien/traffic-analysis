"""System endpoints: health, monitor, models list."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends

from src.adapters.input.web.deps import get_container
from src.adapters.input.web.schemas.inference_config import ModelFileInfo
from src.adapters.input.web.schemas.system import (
    GPUInfo,
    HealthResponse,
    SystemMonitorResponse,
)
from src.bootstrap.container import Container
from src.bootstrap.paths import DEFAULT_MODELS_DIR

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
