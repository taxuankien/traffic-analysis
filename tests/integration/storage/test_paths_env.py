"""Phase 1 web migration: paths.py phải resolve env vars trước khi fallback PROJECT_ROOT."""
from __future__ import annotations

import importlib
import os

import pytest


def test_default_dirs_pickup_env_vars(tmp_path, monkeypatch):
    data_dir = tmp_path / "custom_data"
    models_dir = tmp_path / "custom_models"
    config_dir = tmp_path / "custom_config"
    data_dir.mkdir()
    models_dir.mkdir()
    config_dir.mkdir()

    monkeypatch.setenv("TRAFFIC_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TRAFFIC_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("TRAFFIC_CONFIG_DIR", str(config_dir))

    from src.bootstrap import paths as paths_module

    reloaded = importlib.reload(paths_module)

    assert reloaded.DEFAULT_DATA_DIR == data_dir.resolve()
    assert reloaded.DEFAULT_MODELS_DIR == models_dir.resolve()
    assert reloaded.DEFAULT_CONFIG_DIR == config_dir.resolve()


def test_default_dirs_fallback_to_project_root(monkeypatch):
    for var in ("TRAFFIC_DATA_DIR", "TRAFFIC_MODELS_DIR", "TRAFFIC_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)

    from src.bootstrap import paths as paths_module

    reloaded = importlib.reload(paths_module)

    assert reloaded.DEFAULT_DATA_DIR == reloaded.PROJECT_ROOT / "data"
    assert reloaded.DEFAULT_MODELS_DIR == reloaded.PROJECT_ROOT / "models"
    assert reloaded.DEFAULT_CONFIG_DIR == reloaded.PROJECT_ROOT / "config"


def test_resolve_model_path_strips_legacy_models_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAFFIC_MODELS_DIR", str(tmp_path))
    from src.bootstrap import paths as paths_module

    reloaded = importlib.reload(paths_module)

    assert reloaded.resolve_model_path("models/yolov8n.pt") == (tmp_path / "yolov8n.pt").resolve()
    assert reloaded.resolve_model_path("yolov8n.pt") == (tmp_path / "yolov8n.pt").resolve()


@pytest.fixture(autouse=True, scope="module")
def _restore_env():
    """Reset paths module to pristine state after this test file."""
    yield
    from src.bootstrap import paths as paths_module

    importlib.reload(paths_module)
