"""Phase 1: ``Container.reload_inference_config()`` reset detector cache.

Invariant kiểm tra: phiên đang chạy không bị ảnh hưởng — vì
``analysis_service()`` build một ``AnalysisService`` mới mỗi lần được gọi và
phiên đang chạy giữ reference riêng đến detector cũ.
"""
from __future__ import annotations

import pytest

pytest.importorskip("ultralytics")  # detector() yêu cầu YOLO + có thể download weights


def test_reload_resets_detector_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAFFIC_MODELS_DIR", str(tmp_path / "models"))

    from src.bootstrap import paths as paths_module
    import importlib

    importlib.reload(paths_module)

    from src.bootstrap.container import Container
    from src.bootstrap.inference_config import InferenceConfig

    cfg = InferenceConfig()
    container = Container(data_dir=tmp_path / "data", inference_config=cfg)

    # Inject a fake detector to avoid pulling weights (we only want to assert cache reset).
    sentinel_old = object()
    container._detector = sentinel_old
    assert container._detector is sentinel_old

    new_cfg = InferenceConfig()
    new_cfg.detection.confidence = 0.42
    container.reload_inference_config(new_cfg)

    assert container.inference_config is new_cfg
    assert container._detector is None  # cache reset


def test_inference_config_repo_uses_explicit_path(tmp_path):
    from src.bootstrap.container import Container
    from src.bootstrap.inference_config import InferenceConfig

    cfg_path = tmp_path / "custom_inference.yaml"
    container = Container(
        data_dir=tmp_path / "data",
        inference_config=InferenceConfig(),
        inference_config_path=cfg_path,
    )

    repo = container.inference_config_repo()
    assert repo.path == cfg_path
