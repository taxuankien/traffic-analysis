"""Concrete monitor: psutil for CPU/RAM, pynvml (preferred) or torch.cuda for GPU.

pynvml gives us real GPU utilization (the same number nvidia-smi shows). When it
is missing we still report VRAM via torch.cuda so the panel is useful on plain
PyTorch installs; ``utilization_percent`` is reported as ``None`` in that case.
"""
from __future__ import annotations

import logging

from src.application.ports.output.system_monitor_port import (
    GPUSnapshot,
    SystemMonitorPort,
    SystemSnapshot,
)

logger = logging.getLogger(__name__)


class SystemMonitor(SystemMonitorPort):
    def __init__(self) -> None:
        self._psutil = self._try_import("psutil")
        self._torch = self._try_import("torch")
        self._pynvml = self._try_import("pynvml")
        self._nvml_ready = False
        if self._pynvml is not None:
            try:
                self._pynvml.nvmlInit()
                self._nvml_ready = True
            except Exception as exc:  # driver missing, no GPU, etc.
                logger.info("pynvml init thất bại, GPU utilization sẽ không khả dụng: %s", exc)
                self._pynvml = None

        # Prime psutil.cpu_percent — first call always returns 0.0 because it needs
        # a previous sample to diff against.
        if self._psutil is not None:
            try:
                self._psutil.cpu_percent(interval=None)
            except Exception:
                pass

    @staticmethod
    def _try_import(name: str):
        try:
            return __import__(name)
        except Exception:
            return None

    def snapshot(self) -> SystemSnapshot:
        cpu = ram_pct = ram_used = ram_total = 0.0
        if self._psutil is not None:
            try:
                cpu = float(self._psutil.cpu_percent(interval=None))
                vm = self._psutil.virtual_memory()
                ram_pct = float(vm.percent)
                ram_used = float(vm.used) / (1024 * 1024)
                ram_total = float(vm.total) / (1024 * 1024)
            except Exception as exc:
                logger.debug("psutil snapshot lỗi: %s", exc)

        return SystemSnapshot(
            cpu_percent=cpu,
            ram_percent=ram_pct,
            ram_used_mb=ram_used,
            ram_total_mb=ram_total,
            gpus=self._gpu_snapshots(),
        )

    def _gpu_snapshots(self) -> list[GPUSnapshot]:
        # Prefer NVML — it reports utilization AND mem, and reflects all processes
        # on the GPU (not just the current Python process).
        if self._nvml_ready:
            try:
                return self._gpu_snapshots_nvml()
            except Exception as exc:
                logger.debug("NVML snapshot lỗi, fallback sang torch: %s", exc)

        if self._torch is not None and getattr(self._torch, "cuda", None) is not None:
            try:
                if self._torch.cuda.is_available():
                    return self._gpu_snapshots_torch()
            except Exception as exc:
                logger.debug("torch.cuda snapshot lỗi: %s", exc)
        return []

    def _gpu_snapshots_nvml(self) -> list[GPUSnapshot]:
        nvml = self._pynvml
        out: list[GPUSnapshot] = []
        count = nvml.nvmlDeviceGetCount()
        for i in range(count):
            handle = nvml.nvmlDeviceGetHandleByIndex(i)
            name_raw = nvml.nvmlDeviceGetName(handle)
            name = name_raw.decode("utf-8", errors="replace") if isinstance(name_raw, bytes) else str(name_raw)
            mem = nvml.nvmlDeviceGetMemoryInfo(handle)
            try:
                util = float(nvml.nvmlDeviceGetUtilizationRates(handle).gpu)
            except Exception:
                util = None
            out.append(
                GPUSnapshot(
                    index=i,
                    name=name,
                    utilization_percent=util,
                    memory_used_mb=mem.used / (1024 * 1024),
                    memory_total_mb=mem.total / (1024 * 1024),
                )
            )
        return out

    def _gpu_snapshots_torch(self) -> list[GPUSnapshot]:
        torch = self._torch
        out: list[GPUSnapshot] = []
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            total_mb = props.total_memory / (1024 * 1024)
            # ``memory_reserved`` reflects the caching allocator footprint, which
            # tracks "what this process is holding" closer than ``memory_allocated``.
            used_mb = torch.cuda.memory_reserved(i) / (1024 * 1024)
            out.append(
                GPUSnapshot(
                    index=i,
                    name=props.name,
                    utilization_percent=None,
                    memory_used_mb=used_mb,
                    memory_total_mb=total_mb,
                )
            )
        return out

    def available_devices(self) -> list[str]:
        devices = ["cpu"]
        if self._torch is not None and getattr(self._torch, "cuda", None) is not None:
            try:
                if self._torch.cuda.is_available():
                    for i in range(self._torch.cuda.device_count()):
                        devices.append(f"cuda:{i}")
            except Exception:
                pass
        return devices

    def __del__(self) -> None:
        if self._nvml_ready and self._pynvml is not None:
            try:
                self._pynvml.nvmlShutdown()
            except Exception:
                pass
