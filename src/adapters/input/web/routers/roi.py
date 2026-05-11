"""ROI config GET/PUT."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, status

from src.adapters.input.web.deps import get_container
from src.adapters.input.web.schemas.roi import (
    CountingLineDTO,
    ROIConfigDTO,
    ROIPolygonDTO,
)
from src.bootstrap.container import Container
from src.domain.entities.roi_config import ROIConfig
from src.domain.exceptions import ROIConfigNotFoundError
from src.domain.value_objects.counting_line import CountingLine, LineDirection
from src.domain.value_objects.roi_polygon import ROIPolygon

router = APIRouter(prefix="/sources/{source_id}/roi", tags=["roi"])


def _to_dto(cfg: ROIConfig) -> ROIConfigDTO:
    return ROIConfigDTO(
        source_id=cfg.source_id,
        reference_frame_index=cfg.reference_frame_index,
        roi_polygons=[ROIPolygonDTO(name=p.name, points=list(p.points)) for p in cfg.roi_polygons],
        counting_lines=[
            CountingLineDTO(
                name=l.name,
                start=l.start,
                end=l.end,
                direction=l.direction.value if hasattr(l.direction, "value") else l.direction,
            )
            for l in cfg.counting_lines
        ],
        pixels_per_meter=cfg.pixels_per_meter,
        detection_roi=cfg.detection_roi,
        created_at=cfg.created_at,
    )


def _from_dto(source_id: str, dto: ROIConfigDTO) -> ROIConfig:
    return ROIConfig(
        source_id=source_id,
        reference_frame_index=dto.reference_frame_index,
        roi_polygons=[ROIPolygon(name=p.name, points=list(p.points)) for p in dto.roi_polygons],
        counting_lines=[
            CountingLine(
                name=l.name,
                start=l.start,
                end=l.end,
                direction=LineDirection(l.direction),
            )
            for l in dto.counting_lines
        ],
        pixels_per_meter=dto.pixels_per_meter,
        detection_roi=dto.detection_roi,
        created_at=dto.created_at or datetime.now(),
    )


@router.get("", response_model=ROIConfigDTO | None)
def get_roi(
    source_id: str, container: Container = Depends(get_container)
) -> ROIConfigDTO | None:
    """Trả về ROI hiện tại; ``null`` (200) nếu chưa cấu hình."""
    container.source_repo.get(source_id)  # 404 nếu source không có
    try:
        cfg = container.roi_config_service().load_config(source_id)
        return _to_dto(cfg)
    except ROIConfigNotFoundError:
        return None


@router.put("", response_model=ROIConfigDTO, status_code=status.HTTP_200_OK)
def put_roi(
    source_id: str,
    body: ROIConfigDTO,
    container: Container = Depends(get_container),
) -> ROIConfigDTO:
    container.source_repo.get(source_id)  # 404 nếu source không có
    config = _from_dto(source_id, body)
    container.roi_config_service().save_config(config)
    return _to_dto(config)
