from __future__ import annotations

from typing import Any

from src.application.ports.input.roi_config_port import ROIConfigPort
from src.application.ports.output.repository_port import (
    ROIConfigRepositoryPort,
    SourceRepositoryPort,
)
from src.application.ports.output.video_reader_port import VideoReaderPort
from src.domain.entities.roi_config import ROIConfig


class ROIConfigService(ROIConfigPort):
    def __init__(
        self,
        source_repo: SourceRepositoryPort,
        roi_repo: ROIConfigRepositoryPort,
        video_reader: VideoReaderPort,
    ) -> None:
        self._sources = source_repo
        self._roi = roi_repo
        self._video = video_reader

    def extract_reference_frame(self, source_id: str, frame_index: int = 0) -> Any:
        source = self._sources.get(source_id)
        return self._video.get_frame(source.path, frame_index)

    def save_config(self, config: ROIConfig) -> None:
        self._sources.get(config.source_id)  # validates existence
        self._roi.save(config)

    def load_config(self, source_id: str) -> ROIConfig:
        return self._roi.load(source_id)

    def has_config(self, source_id: str) -> bool:
        return self._roi.exists(source_id)
