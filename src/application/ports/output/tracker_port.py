from __future__ import annotations

from abc import ABC, abstractmethod

from .detector_port import Detection


class TrackerPort(ABC):
    @abstractmethod
    def update(self, detection: Detection) -> Detection: ...

    @abstractmethod
    def reset(self) -> None: ...
