from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.analysis_session import AnalysisSession
from src.domain.entities.video_source import VideoSource
from src.domain.value_objects.analysis_interval import AnalysisInterval


class DataManagementPort(ABC):
    # Source CRUD
    @abstractmethod
    def add_source(self, name: str, path: str) -> VideoSource: ...

    @abstractmethod
    def list_sources(self) -> list[VideoSource]: ...

    @abstractmethod
    def get_source(self, source_id: str) -> VideoSource: ...

    @abstractmethod
    def delete_source(self, source_id: str) -> None: ...

    # Sessions & results
    @abstractmethod
    def list_sessions(self, source_id: str) -> list[AnalysisSession]: ...

    @abstractmethod
    def query_intervals(
        self,
        source_id: str,
        session_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AnalysisInterval]: ...

    @abstractmethod
    def export_csv(self, source_id: str, session_id: str, target_path: str) -> str: ...
