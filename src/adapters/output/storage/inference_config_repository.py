"""YAML-backed inference config repository.

Sử dụng ``ruamel.yaml`` (round-trip mode) để giữ comment + ordering khi UI
``PUT /api/config/inference`` ghi xuống. Nếu ``ruamel.yaml`` không có sẵn,
fallback ``pyyaml`` — comment sẽ mất, nhưng file vẫn valid.

Atomic write: ghi file ``.tmp`` cùng directory rồi ``os.replace()`` sang
target để tránh corrupt khi process bị kill giữa chừng.
"""
from __future__ import annotations

import logging
import os
from io import StringIO
from pathlib import Path
from typing import Any

from src.application.ports.output.inference_config_repository_port import (
    InferenceConfigRepositoryPort,
)
from src.bootstrap.inference_config import InferenceConfig

logger = logging.getLogger(__name__)


class FileSystemInferenceConfigRepository(InferenceConfigRepositoryPort):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> InferenceConfig:
        if not self._path.is_file():
            raise FileNotFoundError(
                f"Không tìm thấy file inference config tại {self._path}"
            )
        return InferenceConfig.load(self._path)

    def save(self, config: InferenceConfig) -> None:
        payload = _config_to_mapping(config)
        text = _serialize_yaml(payload, source_path=self._path if self._path.is_file() else None)
        self._atomic_write(text)

    def reset_to_defaults(self) -> InferenceConfig:
        defaults = InferenceConfig()
        self.save(defaults)
        defaults.source_path = self._path
        return defaults

    # --- internals -----------------------------------------------------------

    def _atomic_write(self, text: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self._path)


def _config_to_mapping(config: InferenceConfig) -> dict[str, Any]:
    """Build a plain mapping mirror of ``InferenceConfig`` suitable for YAML dump.

    Phải khớp đúng với section schema mà ``InferenceConfig._from_mapping``
    chấp nhận để round-trip ``load → save → load`` cho cùng kết quả.
    """
    return {
        "model": {
            "weights": config.model.weights,
            "device": config.model.device,
            "imgsz": int(config.model.imgsz),
            "half": bool(config.model.half),
            "max_det": int(config.model.max_det),
            "agnostic_nms": bool(config.model.agnostic_nms),
        },
        "detection": {
            "confidence": float(config.detection.confidence),
            "iou": float(config.detection.iou),
            "class_ids": list(config.detection.class_ids),
        },
        "detection_roi": {
            "enabled": bool(config.detection_roi.enabled),
            "bounds": [float(v) for v in config.detection_roi.bounds],
        },
        "tracking": {
            "track_activation_threshold": float(config.tracking.track_activation_threshold),
            "lost_track_buffer": int(config.tracking.lost_track_buffer),
            "minimum_matching_threshold": float(config.tracking.minimum_matching_threshold),
            "minimum_consecutive_frames": int(config.tracking.minimum_consecutive_frames),
        },
        "speed": {"min_frames": int(config.speed.min_frames)},
        "analysis": {
            "default_interval_seconds": float(config.analysis.default_interval_seconds),
            "frame_skip": int(config.analysis.frame_skip),
        },
        "queue": {
            "stopped_speed_kmh": float(config.queue.stopped_speed_kmh),
            "window_frames": int(config.queue.window_frames),
        },
        "vehicle_pce": config.vehicle_pce.as_mapping(),
    }


def _serialize_yaml(data: dict[str, Any], source_path: Path | None) -> str:
    """Serialize mapping → YAML string, ưu tiên giữ comment qua ruamel.yaml.

    Khi ``source_path`` tồn tại và ``ruamel.yaml`` khả dụng, đọc file gốc theo
    round-trip mode rồi chỉ cập nhật scalar values — comment, ordering, anchors
    được bảo toàn. Khi không, dump bằng pyyaml (mất comment).
    """
    try:
        from ruamel.yaml import YAML  # type: ignore
    except ImportError:
        return _dump_with_pyyaml(data)

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    if source_path is not None and source_path.is_file():
        try:
            with source_path.open("r", encoding="utf-8") as f:
                doc = yaml.load(f) or {}
            _deep_update(doc, data)
            buf = StringIO()
            yaml.dump(doc, buf)
            return buf.getvalue()
        except Exception as exc:  # noqa: BLE001 — fall back, preserve comment is best-effort
            logger.warning(
                "ruamel round-trip thất bại (%s), fallback dump không giữ comment.", exc
            )

    buf = StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def _dump_with_pyyaml(data: dict[str, Any]) -> str:
    import yaml  # type: ignore

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _deep_update(target: Any, source: Any) -> None:
    """Recursively replace scalar leaves in ``target`` with values from ``source``,
    preserving any keys/comment in ``target`` that ``source`` doesn't override
    (ruamel keeps the original CommentedMap structure when we mutate in place).
    """
    if isinstance(source, dict) and hasattr(target, "__setitem__"):
        for k, v in source.items():
            if k in target and isinstance(target[k], (dict, list)) and isinstance(v, (dict, list)):
                _deep_update(target[k], v)
            else:
                target[k] = v
        # Drop keys that no longer exist in source so we don't keep stale data.
        stale = [k for k in list(target.keys()) if k not in source]
        for k in stale:
            del target[k]
    elif isinstance(source, list) and hasattr(target, "__setitem__"):
        target.clear()
        for item in source:
            target.append(item)
