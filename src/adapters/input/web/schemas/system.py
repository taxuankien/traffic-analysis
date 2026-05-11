from __future__ import annotations

from pydantic import BaseModel


class GPUInfo(BaseModel):
    name: str
    util_percent: float | None = None
    mem_used_mb: float | None = None
    mem_total_mb: float | None = None


class SystemMonitorResponse(BaseModel):
    cpu_percent: float
    ram_percent: float
    gpu: list[GPUInfo] = []


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0"
