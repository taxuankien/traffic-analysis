from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.domain.entities.roi_config import ROIConfig


class ROIConfigPort(ABC):
    @abstractmethod
    def extract_reference_frame(self, source_id: str, frame_index: int = 0) -> Any:
        """Return the frame as a numpy ndarray for ROI editing."""

    @abstractmethod
    def save_config(self, config: ROIConfig) -> None: ...

    @abstractmethod
    def load_config(self, source_id: str) -> ROIConfig: ...

    @abstractmethod
    def has_config(self, source_id: str) -> bool: ...
