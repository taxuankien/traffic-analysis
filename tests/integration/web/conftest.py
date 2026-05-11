from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.adapters.input.web.app import create_app
from src.bootstrap.container import Container
from src.bootstrap.inference_config import InferenceConfig


@pytest.fixture
def container(tmp_path: Path) -> Container:
    cfg = InferenceConfig()
    cfg.source_path = tmp_path / "config" / "inference.yaml"
    cfg.source_path.parent.mkdir(parents=True, exist_ok=True)
    # Seed YAML so PUT round-trip can preserve structure.
    from src.adapters.output.storage.inference_config_repository import (
        FileSystemInferenceConfigRepository,
    )

    repo = FileSystemInferenceConfigRepository(cfg.source_path)
    repo.save(cfg)
    return Container(
        data_dir=tmp_path / "data",
        inference_config=cfg,
        inference_config_path=cfg.source_path,
    )


@pytest.fixture
def client(container: Container) -> TestClient:
    app = create_app(container=container)
    return TestClient(app)
