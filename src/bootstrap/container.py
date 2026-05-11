from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.adapters.output.detection.bytetrack_tracker import SVByteTracker
from src.adapters.output.detection.yolo_detector import YOLODetector
from src.adapters.output.monitoring.system_monitor import SystemMonitor
from src.adapters.output.storage.artifact_repository import (
    FileSystemArtifactRepository,
)
from src.adapters.output.storage.csv_repository import CSVIntervalRepository
from src.adapters.output.storage.inference_config_repository import (
    FileSystemInferenceConfigRepository,
)
from src.adapters.output.storage.json_repository import (
    JSONROIConfigRepository,
    JSONSessionRepository,
    JSONSourceRepository,
)
from src.adapters.output.video.sv_video_reader import SVVideoReader
from src.application.ports.output.artifact_repository_port import (
    ArtifactRepositoryPort,
)
from src.application.ports.output.inference_config_repository_port import (
    InferenceConfigRepositoryPort,
)
from src.application.ports.output.system_monitor_port import SystemMonitorPort
from src.application.services.analysis_service import AnalysisService
from src.application.services.data_management_service import DataManagementService
from src.application.services.frame_extraction_service import FrameExtractionService
from src.application.services.roi_config_service import ROIConfigService
from src.application.services.visualization_service import VisualizationService
from src.bootstrap.inference_config import InferenceConfig


@dataclass
class Container:
    data_dir: Path
    inference_config: InferenceConfig = field(default_factory=InferenceConfig)
    weights_path: str | None = None  # explicit override; None → use inference_config.model.weights
    inference_config_path: Path | None = None  # YAML path for repo; None → use inference_config.source_path

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._source_repo = JSONSourceRepository(self.data_dir)
        self._roi_repo = JSONROIConfigRepository(self.data_dir)
        self._session_repo = JSONSessionRepository(self.data_dir)
        self._interval_repo = CSVIntervalRepository(self.data_dir)
        self._video_reader = SVVideoReader()
        self._detector: YOLODetector | None = None
        self._system_monitor: SystemMonitorPort | None = None
        self._inference_repo: InferenceConfigRepositoryPort | None = None
        # ``None`` means "use ``inference_config.model.device``"; any other value
        # (including the string "cpu") wins over the YAML-level setting.
        self._device_override: str | None = None

    @property
    def source_repo(self):
        return self._source_repo

    @property
    def roi_repo(self):
        return self._roi_repo

    @property
    def session_repo(self):
        return self._session_repo

    @property
    def interval_repo(self):
        return self._interval_repo

    @property
    def video_reader(self):
        return self._video_reader

    def _resolved_weights(self) -> str:
        return self.weights_path or self.inference_config.model.weights

    def _resolved_device(self) -> str | None:
        return self._device_override if self._device_override is not None else self.inference_config.model.device

    def set_device_override(self, device: str | None) -> None:
        """Override ``model.device`` for subsequent service calls.

        Pass ``None`` to revert to the YAML/default value. Resets the cached
        detector so the next ``detector()`` call rebuilds with the new device.
        Use the empty string interchangeably with ``None`` (GUI convenience).
        """
        normalized = device.strip() if isinstance(device, str) else device
        if normalized == "":
            normalized = None
        if normalized == self._device_override:
            return
        self._device_override = normalized
        self._detector = None

    def detector(self) -> YOLODetector:
        if self._detector is None:
            m = self.inference_config.model
            d = self.inference_config.detection
            r = self.inference_config.detection_roi
            self._detector = YOLODetector(
                weights=self._resolved_weights(),
                confidence=d.confidence,
                iou=d.iou,
                class_ids=d.class_ids,
                device=self._resolved_device(),
                imgsz=m.imgsz,
                half=m.half,
                max_det=m.max_det,
                agnostic_nms=m.agnostic_nms,
                roi_bounds=tuple(r.bounds) if r.enabled and not r.is_full_frame() else None,
            )
        return self._detector

    def system_monitor(self) -> SystemMonitorPort:
        if self._system_monitor is None:
            self._system_monitor = SystemMonitor()
        return self._system_monitor

    def tracker(self, frame_rate: int = 30) -> SVByteTracker:
        # Always return fresh instance to avoid reusing state between sessions
        t = self.inference_config.tracking
        return SVByteTracker(
            track_activation_threshold=t.track_activation_threshold,
            lost_track_buffer=t.lost_track_buffer,
            minimum_matching_threshold=t.minimum_matching_threshold,
            frame_rate=frame_rate,
            minimum_consecutive_frames=t.minimum_consecutive_frames,
        )

    def data_management_service(self) -> DataManagementService:
        return DataManagementService(
            source_repo=self._source_repo,
            session_repo=self._session_repo,
            interval_repo=self._interval_repo,
            data_dir=self.data_dir,
        )

    def roi_config_service(self) -> ROIConfigService:
        return ROIConfigService(
            source_repo=self._source_repo,
            roi_repo=self._roi_repo,
            video_reader=self._video_reader,
        )

    def analysis_service(self, frame_rate: int = 30) -> AnalysisService:
        q = self.inference_config.queue
        a = self.inference_config.analysis
        return AnalysisService(
            source_repo=self._source_repo,
            roi_repo=self._roi_repo,
            session_repo=self._session_repo,
            interval_repo=self._interval_repo,
            video_reader=self._video_reader,
            detector=self.detector(),
            tracker=self.tracker(frame_rate=frame_rate),
            speed_min_frames=self.inference_config.speed.min_frames,
            default_interval_seconds=a.default_interval_seconds,
            queue_speed_kmh=q.stopped_speed_kmh,
            queue_window_frames=q.window_frames,
            frame_skip=a.frame_skip,
        )

    def visualization_service(self, frame_rate: int = 30) -> VisualizationService:
        return VisualizationService(
            source_repo=self._source_repo,
            roi_repo=self._roi_repo,
            video_reader=self._video_reader,
            detector=self.detector(),
            tracker=self.tracker(frame_rate=frame_rate),
        )

    def frame_extraction_service(self) -> FrameExtractionService:
        return FrameExtractionService(
            source_repo=self._source_repo,
            video_reader=self._video_reader,
            detector=self.detector(),
            frames_dir=self.data_dir / "frames",
        )

    # --- Inference config repo & hot-reload ----------------------------------

    def artifact_repo(self) -> ArtifactRepositoryPort:
        if not hasattr(self, "_artifact_repo") or self._artifact_repo is None:
            self._artifact_repo = FileSystemArtifactRepository(self.data_dir)
        return self._artifact_repo

    def inference_config_repo(self) -> InferenceConfigRepositoryPort:
        """Repo cho UI ``GET/PUT /api/config/inference``.

        Resolve YAML path theo thứ tự: ``inference_config_path`` (explicit) →
        ``inference_config.source_path`` (file đã load) → mặc định
        ``${TRAFFIC_CONFIG_DIR}/inference.yaml``.
        """
        if self._inference_repo is None:
            from src.bootstrap.paths import DEFAULT_CONFIG_DIR

            path = (
                self.inference_config_path
                or self.inference_config.source_path
                or DEFAULT_CONFIG_DIR / "inference.yaml"
            )
            self._inference_repo = FileSystemInferenceConfigRepository(path)
        return self._inference_repo

    def reload_inference_config(self, new_config: InferenceConfig) -> None:
        """Áp dụng ``new_config`` cho mọi ``analysis_service()`` được tạo SAU lời gọi này.

        - Reset cache ``_detector`` để build lại với weights/imgsz/device mới.
        - Phiên đang chạy giữ instance cũ (capture by reference khi
          ``analysis_service()`` được gọi) — không bị ảnh hưởng. Đây là
          invariant quan trọng, có test bảo đảm.
        """
        self.inference_config = new_config
        self._detector = None
