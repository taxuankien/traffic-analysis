"""Port for monitoring runtime resource usage (CPU, RAM, GPU).

Decoupled from the concrete monitoring backend (psutil/pynvml/torch) so the GUI
and CLI can show live stats without depending on a specific library.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GPUSnapshot:
    index: int
    name: str
    utilization_percent: float | None  # None when nvidia-ml-py is unavailable
    memory_used_mb: float
    memory_total_mb: float

    @property
    def memory_percent(self) -> float:
        if self.memory_total_mb <= 0:
            return 0.0
        return self.memory_used_mb / self.memory_total_mb * 100.0


@dataclass
class SystemSnapshot:
    cpu_percent: float
    ram_percent: float
    ram_used_mb: float
    ram_total_mb: float
    gpus: list[GPUSnapshot]

    @property
    def has_gpu(self) -> bool:
        return bool(self.gpus)


class SystemMonitorPort(ABC):
    @abstractmethod
    def snapshot(self) -> SystemSnapshot:
        """Return a one-shot reading of CPU/RAM/GPU usage."""

    @abstractmethod
    def available_devices(self) -> list[str]:
        """List device strings ultralytics/torch accept (e.g. ['cpu', 'cuda:0'])."""
