from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import supervision as sv
from ultralytics import YOLO

from src.application.ports.output.detector_port import Detection, DetectorPort
from src.bootstrap.paths import DEFAULT_MODELS_DIR, PROJECT_ROOT
from src.domain.value_objects.vehicle_type import VEHICLE_CLASS_IDS


class YOLODetector(DetectorPort):
    # Ultralytics predict defaults — keep these aligned so we don't undercount
    # versus a vanilla `model(frame)` call.
    _ULTRALYTICS_CONF = 0.25
    _ULTRALYTICS_IOU = 0.7

    def __init__(
        self,
        weights: str = "yolov8x.pt",
        confidence: float | None = None,
        iou: float | None = None,
        class_ids: Iterable[int] | None = None,
        device: str | None = None,
        imgsz: int | None = None,
        half: bool = False,
        max_det: int | None = None,
        agnostic_nms: bool = False,
        roi_bounds: tuple[float, float, float, float] | None = None,
    ) -> None:
        self._weights = self._resolve_weights(weights)
        self._model = YOLO(self._weights)
        self._confidence = confidence if confidence is not None else self._ULTRALYTICS_CONF
        self._iou = iou if iou is not None else self._ULTRALYTICS_IOU
        self._class_ids = list(class_ids) if class_ids is not None else list(VEHICLE_CLASS_IDS)
        self._device = device
        self._imgsz = imgsz
        self._half = half
        self._max_det = max_det
        self._agnostic_nms = agnostic_nms
        # ``_default_roi_bounds`` is the construction-time value (e.g. YAML default);
        # ``_roi_bounds`` is the active value, which per-source configs can override.
        self._default_roi_bounds = roi_bounds
        self._roi_bounds = roi_bounds  # normalized (x_min, y_min, x_max, y_max) or None

    def set_roi_bounds(
        self, bounds: tuple[float, float, float, float] | None
    ) -> None:
        """Override the active ROI for subsequent ``detect()`` calls.

        Pass ``None`` to revert to the construction-time default (typically the
        ``detection_roi`` from ``inference.yaml``). Callers do not need to validate
        bounds — invalid/full-frame values are tolerated by ``_compute_crop_offset``.
        """
        self._roi_bounds = bounds if bounds is not None else self._default_roi_bounds

    @staticmethod
    def _resolve_weights(weights: str) -> str:
        """Tìm file weights theo thứ tự ưu tiên (Phase 1 web migration):
            1. tuyệt đối → giữ nguyên
            2. relative theo CWD → resolve nếu tồn tại
            3. relative theo ``TRAFFIC_MODELS_DIR`` (== ``DEFAULT_MODELS_DIR``) — strip
               prefix ``models/`` nếu có, neo phần còn lại vào models dir.
            4. relative theo PROJECT_ROOT (legacy)
            5. fallback: giữ nguyên chuỗi để Ultralytics tự download.
        """
        candidate = Path(weights)
        if candidate.is_absolute():
            return str(candidate)
        if candidate.is_file():
            return str(candidate.resolve())
        # Strip leading "models/" so legacy YAML "models/yolo11x.pt" resolves
        # cleanly even when MODELS_DIR is mounted to /app/models in Docker.
        parts = candidate.parts
        stripped = Path(*parts[1:]) if parts and parts[0] == "models" and len(parts) > 1 else candidate
        in_models = (DEFAULT_MODELS_DIR / stripped).resolve()
        if in_models.is_file():
            return str(in_models)
        rooted = (PROJECT_ROOT / candidate).resolve()
        if rooted.is_file():
            return str(rooted)
        # Fallback: let Ultralytics download into MODELS_DIR. Only do this for
        # bare filenames (no slashes) to avoid silently downloading something
        # the user mistyped as a path.
        if not parts or len(parts) == 1:
            return str(DEFAULT_MODELS_DIR / candidate)
        return weights

    def detect(self, frame: Any) -> Detection:
        kwargs: dict[str, Any] = {
            "verbose": False,
            "conf": self._confidence,
            "iou": self._iou,
        }
        if self._device:
            kwargs["device"] = self._device
        if self._imgsz is not None:
            kwargs["imgsz"] = self._imgsz
        if self._half:
            kwargs["half"] = True
        if self._max_det is not None:
            kwargs["max_det"] = self._max_det
        if self._agnostic_nms:
            kwargs["agnostic_nms"] = True

        crop_offset = self._compute_crop_offset(frame)
        if crop_offset is not None:
            x1, y1, x2, y2 = crop_offset
            input_frame = frame[y1:y2, x1:x2]
        else:
            input_frame = frame

        results = self._model(input_frame, **kwargs)[0]
        detections = sv.Detections.from_ultralytics(results)
        if crop_offset is not None and len(detections) > 0:
            x1, y1, _, _ = crop_offset
            detections.xyxy = detections.xyxy + np.array([x1, y1, x1, y1], dtype=detections.xyxy.dtype)
        if detections.class_id is not None and self._class_ids:
            mask = np.isin(detections.class_id, self._class_ids)
            detections = detections[mask]
        return Detection(raw=detections)

    def _compute_crop_offset(self, frame: Any) -> tuple[int, int, int, int] | None:
        """Resolve normalized ROI bounds to absolute pixel coords for the current frame.

        Returns ``None`` when no ROI is configured or the resolved crop would be empty
        (e.g. degenerate after rounding on a tiny frame), in which case the caller falls
        back to processing the full frame.
        """
        if self._roi_bounds is None:
            return None
        h, w = frame.shape[:2]
        x_min, y_min, x_max, y_max = self._roi_bounds
        x1 = max(0, min(w, int(round(x_min * w))))
        y1 = max(0, min(h, int(round(y_min * h))))
        x2 = max(0, min(w, int(round(x_max * w))))
        y2 = max(0, min(h, int(round(y_max * h))))
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    @property
    def class_names(self) -> dict[int, str]:
        return self._model.model.names
