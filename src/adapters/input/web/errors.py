"""Domain exception → HTTPException mapping.

Đăng ký exception handlers ở app factory để mọi router gọi service trực tiếp,
không cần wrap try/except boilerplate.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.domain.exceptions import (
    AnalysisSessionNotFoundError,
    CalibrationError,
    InvalidROIConfigError,
    ROIConfigNotFoundError,
    VideoSourceNotFoundError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(VideoSourceNotFoundError)
    async def _not_found_source(_: Request, exc: VideoSourceNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(AnalysisSessionNotFoundError)
    async def _not_found_session(_: Request, exc: AnalysisSessionNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(ROIConfigNotFoundError)
    async def _not_found_roi(_: Request, exc: ROIConfigNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(InvalidROIConfigError)
    async def _bad_roi(_: Request, exc: InvalidROIConfigError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)

    @app.exception_handler(CalibrationError)
    async def _calibration(_: Request, exc: CalibrationError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_400_BAD_REQUEST)

    @app.exception_handler(FileNotFoundError)
    async def _file_not_found(_: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_404_NOT_FOUND)
