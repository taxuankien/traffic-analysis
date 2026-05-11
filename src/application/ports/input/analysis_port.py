from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from src.domain.entities.analysis_session import AnalysisSession


@dataclass
class AnalysisProgress:
    session_id: str
    current_frame: int
    total_frames: int
    elapsed_seconds: float
    intervals_completed: int


ProgressCallback = Callable[[AnalysisProgress], None]


class AnalysisPort(ABC):
    @abstractmethod
    def start_session(
        self, source_id: str, interval_seconds: float | None = None
    ) -> AnalysisSession: ...

    @abstractmethod
    def run_session(
        self,
        session_id: str,
        progress_cb: ProgressCallback | None = None,
        annotated_output_path: str | None = None,
    ) -> AnalysisSession: ...
