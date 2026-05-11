"""Project path anchors.

Mọi đường dẫn mặc định trong dự án phải neo theo các hằng ở module này
thay vì dựng lại ``Path(__file__).resolve().parents[N]`` ở mỗi nơi sử dụng,
để chương trình vẫn chạy đúng khi cây thư mục bị di chuyển hoặc deploy
trong container Docker (mount-point khác).

Thứ tự resolve (mới — Phase 1 web migration):
    DATA_DIR    ← env ``TRAFFIC_DATA_DIR``    || ``PROJECT_ROOT/data``
    MODELS_DIR  ← env ``TRAFFIC_MODELS_DIR``  || ``PROJECT_ROOT/models``
    CONFIG_DIR  ← env ``TRAFFIC_CONFIG_DIR``  || ``PROJECT_ROOT/config``
    RESULT_DIR  ← env ``TRAFFIC_RESULT_DIR``  || ``PROJECT_ROOT/result``
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def _env_path(env_name: str, fallback: Path) -> Path:
    value = os.environ.get(env_name)
    if value:
        return Path(value).expanduser().resolve()
    return fallback


DEFAULT_DATA_DIR: Path = _env_path("TRAFFIC_DATA_DIR", PROJECT_ROOT / "data")
DEFAULT_MODELS_DIR: Path = _env_path("TRAFFIC_MODELS_DIR", PROJECT_ROOT / "models")
DEFAULT_CONFIG_DIR: Path = _env_path("TRAFFIC_CONFIG_DIR", PROJECT_ROOT / "config")
DEFAULT_RESULT_DIR: Path = _env_path("TRAFFIC_RESULT_DIR", PROJECT_ROOT / "result")


def resolve_under_root(path: str | Path) -> Path:
    """Trả về ``Path`` tuyệt đối; đường dẫn tương đối được neo vào ``PROJECT_ROOT``."""
    p = Path(path)
    if p.is_absolute():
        return p
    return (PROJECT_ROOT / p).resolve()


def resolve_model_path(path: str | Path) -> Path:
    """Resolve weights path; relative path neo theo ``DEFAULT_MODELS_DIR``.

    Hỗ trợ 3 dạng input:
        - tuyệt đối → giữ nguyên
        - bắt đầu bằng ``models/`` → strip prefix rồi neo lại (legacy YAML)
        - tên file thuần (``yolov8n.pt``) → ``MODELS_DIR / name``
    """
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    parts = p.parts
    if parts and parts[0] == "models":
        p = Path(*parts[1:]) if len(parts) > 1 else Path()
    return (DEFAULT_MODELS_DIR / p).resolve()
