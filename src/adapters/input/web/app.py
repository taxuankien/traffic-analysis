"""FastAPI app factory.

Stand-up:
    uvicorn src.adapters.input.web.app:create_app --factory --reload \
        --host 0.0.0.0 --port 8000

Container DI sống ở ``app.state.container``. Test suite override qua:
    app.state.container = test_container
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.adapters.input.web.errors import register_exception_handlers
from src.adapters.input.web.jobs import JobManager
from src.adapters.input.web.routers import (
    analysis,
    downloads,
    frames,
    inference_config,
    roi,
    sources,
    system,
)
from src.adapters.input.web.ws import router as ws_router
from src.bootstrap.container import Container
from src.bootstrap.inference_config import InferenceConfig
from src.bootstrap.paths import DEFAULT_CONFIG_DIR, DEFAULT_DATA_DIR

logger = logging.getLogger(__name__)


def _build_container_from_env() -> Container:
    data_dir = DEFAULT_DATA_DIR
    inference_path_env = os.environ.get("TRAFFIC_INFERENCE_CONFIG")
    inference_path = (
        Path(inference_path_env)
        if inference_path_env
        else DEFAULT_CONFIG_DIR / "inference.yaml"
    )
    if inference_path.is_file():
        cfg = InferenceConfig.load(inference_path)
    else:
        logger.warning("Không tìm thấy %s — dùng InferenceConfig mặc định.", inference_path)
        cfg = InferenceConfig()
        cfg.source_path = inference_path  # so save() writes here later

    return Container(
        data_dir=data_dir,
        inference_config=cfg,
        inference_config_path=inference_path,
    )


def _parse_origins() -> list[str]:
    raw = os.environ.get("TRAFFIC_WEB_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app(container: Container | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):  # pragma: no cover — wired below
        try:
            yield
        finally:
            jobs = getattr(app.state, "jobs", None)
            if jobs is not None:
                jobs.shutdown(wait=False)

    app = FastAPI(
        title="Traffic Analysis API",
        version="1.0",
        description="Web-based driving adapter cho hệ thống traffic-analysis.",
        lifespan=lifespan,
    )
    app.state.container = container or _build_container_from_env()
    max_jobs = int(os.environ.get("TRAFFIC_MAX_JOBS", "1"))
    app.state.jobs = JobManager(app.state.container, max_workers=max_jobs)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Routers
    api_prefix = "/api"
    app.include_router(sources.router, prefix=api_prefix)
    app.include_router(frames.router, prefix=api_prefix)
    app.include_router(roi.router, prefix=api_prefix)
    app.include_router(analysis.router, prefix=api_prefix)
    app.include_router(inference_config.router, prefix=api_prefix)
    app.include_router(system.router, prefix=api_prefix)
    app.include_router(downloads.router, prefix=api_prefix)
    app.include_router(ws_router)  # WebSocket — no /api prefix

    # Static files: serve frames + exports for direct browser access.
    container = app.state.container
    frames_dir = container.data_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/files/frames", StaticFiles(directory=frames_dir), name="frames")

    exports_dir = container.data_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/files/exports", StaticFiles(directory=exports_dir), name="exports")

    # SPA dist — check both Docker path and local dev path.
    spa_candidates = [
        Path("/app/frontend/dist"),
        Path(__file__).resolve().parents[4] / "frontend" / "dist",
    ]
    for spa_dist in spa_candidates:
        if spa_dist.is_dir():
            app.mount("/", StaticFiles(directory=spa_dist, html=True), name="spa")
            break

    return app
