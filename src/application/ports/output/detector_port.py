from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Detection:
    """Backend-agnostic detection container.

    Wraps the underlying ``sv.Detections`` so that downstream code can stay decoupled from
    supervision in places that don't need its concrete API. Adapters bridge this gap by
    exposing the underlying object via the ``raw`` attribute when needed.
    """

    raw: Any  # supervision.Detections in concrete adapter


class DetectorPort(ABC):
    @abstractmethod
    def detect(self, frame: Any) -> Detection:
        """Run detection on a single frame and return vehicle-only detections."""
