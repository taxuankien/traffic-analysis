"""FastAPI dependency helpers.

Container DI sống ở ``app.state.container``; mọi router lấy services qua
helpers ở module này thay vì global singleton — tốt cho test (override qua
``app.dependency_overrides``).
"""
from __future__ import annotations

from fastapi import Request

from src.bootstrap.container import Container


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container
