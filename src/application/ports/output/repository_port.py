from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.analysis_session import AnalysisSession
from src.domain.entities.roi_config import ROIConfig
from src.domain.entities.video_source import VideoSource
from src.domain.value_objects.analysis_interval import AnalysisInterval


class SourceRepositoryPort(ABC):
    @abstractmethod
    def save(self, source: VideoSource) -> None: ...

    @abstractmethod
    def list_all(self) -> list[VideoSource]: ...

    @abstractmethod
    def get(self, source_id: str) -> VideoSource: ...

    @abstractmethod
    def delete(self, source_id: str) -> None: ...


class ROIConfigRepositoryPort(ABC):
    @abstractmethod
    def save(self, config: ROIConfig) -> None: ...

    @abstractmethod
    def load(self, source_id: str) -> ROIConfig: ...

    @abstractmethod
    def exists(self, source_id: str) -> bool: ...


class SessionRepositoryPort(ABC):
    @abstractmethod
    def save(self, session: AnalysisSession) -> None: ...

    @abstractmethod
    def list_for_source(self, source_id: str) -> list[AnalysisSession]: ...

    @abstractmethod
    def get(self, source_id: str, session_id: str) -> AnalysisSession: ...


class IntervalRepositoryPort(ABC):
    @abstractmethod
    def append(self, source_id: str, session_id: str, interval: AnalysisInterval) -> None: ...

    @abstractmethod
    def list(
        self,
        source_id: str,
        session_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[AnalysisInterval]: ...

    @abstractmethod
    def csv_path(self, source_id: str, session_id: str) -> str: ...
