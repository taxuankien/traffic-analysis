"""Phase 1: ``FileSystemInferenceConfigRepository`` round-trip + atomic write."""
from __future__ import annotations

import textwrap

import pytest

from src.adapters.output.storage.inference_config_repository import (
    FileSystemInferenceConfigRepository,
)
from src.bootstrap.inference_config import InferenceConfig


def _seed_yaml(path):
    path.write_text(
        textwrap.dedent(
            """
            model:
              weights: "models/yolo11m.pt"
              device: null
              imgsz: 960
              half: false
              max_det: 1000
              agnostic_nms: false
            detection:
              confidence: 0.15
              iou: 0.4
              class_ids: [2, 3, 5, 7]
            detection_roi:
              enabled: false
              bounds: [0.0, 0.0, 1.0, 1.0]
            tracking:
              track_activation_threshold: 0.25
              lost_track_buffer: 30
              minimum_matching_threshold: 0.8
              minimum_consecutive_frames: 3
            speed:
              min_frames: 5
            analysis:
              default_interval_seconds: 30.0
              frame_skip: 1
            queue:
              stopped_speed_kmh: 5.0
              window_frames: 5
            vehicle_pce:
              car: 1.0
              motorcycle: 0.25
              bus: 3.0
              truck: 2.5
            """
        ).strip(),
        encoding="utf-8",
    )


def test_load_returns_inference_config(tmp_path):
    yaml_file = tmp_path / "inference.yaml"
    _seed_yaml(yaml_file)
    repo = FileSystemInferenceConfigRepository(yaml_file)

    cfg = repo.load()

    assert cfg.model.imgsz == 960
    assert cfg.detection.confidence == pytest.approx(0.15)
    assert cfg.tracking.lost_track_buffer == 30


def test_save_round_trip_preserves_values(tmp_path):
    yaml_file = tmp_path / "inference.yaml"
    _seed_yaml(yaml_file)
    repo = FileSystemInferenceConfigRepository(yaml_file)

    cfg = repo.load()
    cfg.detection.confidence = 0.42
    cfg.model.imgsz = 1280
    cfg.tracking.lost_track_buffer = 60
    cfg.vehicle_pce.car = 1.5

    repo.save(cfg)

    reloaded = repo.load()
    assert reloaded.detection.confidence == pytest.approx(0.42)
    assert reloaded.model.imgsz == 1280
    assert reloaded.tracking.lost_track_buffer == 60
    assert reloaded.vehicle_pce.car == pytest.approx(1.5)


def test_save_is_atomic_no_tmp_leftover(tmp_path):
    yaml_file = tmp_path / "inference.yaml"
    _seed_yaml(yaml_file)
    repo = FileSystemInferenceConfigRepository(yaml_file)

    cfg = repo.load()
    cfg.detection.confidence = 0.30
    repo.save(cfg)

    # No .tmp left behind.
    assert not list(tmp_path.glob("*.tmp"))
    # Target still exists with new value.
    assert yaml_file.is_file()


def test_reset_to_defaults_writes_default_yaml(tmp_path):
    yaml_file = tmp_path / "inference.yaml"
    _seed_yaml(yaml_file)
    repo = FileSystemInferenceConfigRepository(yaml_file)

    defaults = repo.reset_to_defaults()
    expected_default = InferenceConfig().model.imgsz
    assert defaults.model.imgsz == expected_default

    reloaded = repo.load()
    assert reloaded.model.imgsz == expected_default


def test_load_missing_file_raises(tmp_path):
    repo = FileSystemInferenceConfigRepository(tmp_path / "missing.yaml")
    with pytest.raises(FileNotFoundError):
        repo.load()
