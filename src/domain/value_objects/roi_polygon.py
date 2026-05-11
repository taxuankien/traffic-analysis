from __future__ import annotations

from dataclasses import dataclass

from src.domain.exceptions import InvalidROIConfigError


@dataclass(frozen=True)
class ROIPolygon:
    name: str
    points: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise InvalidROIConfigError("ROIPolygon.name is required")
        if len(self.points) < 3:
            raise InvalidROIConfigError(
                f"ROIPolygon '{self.name}' needs >= 3 points, got {len(self.points)}"
            )

    @classmethod
    def from_points(cls, name: str, points: list[tuple[int, int]]) -> "ROIPolygon":
        return cls(name=name, points=tuple((int(x), int(y)) for x, y in points))

    def to_dict(self) -> dict:
        return {"name": self.name, "points": [list(p) for p in self.points]}

    @classmethod
    def from_dict(cls, data: dict) -> "ROIPolygon":
        return cls.from_points(data["name"], data["points"])
