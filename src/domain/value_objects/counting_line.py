from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.domain.exceptions import InvalidROIConfigError


class LineDirection(str, Enum):
    IN = "in"
    OUT = "out"
    BOTH = "both"


@dataclass(frozen=True)
class CountingLine:
    name: str
    start: tuple[int, int]
    end: tuple[int, int]
    direction: LineDirection = LineDirection.BOTH

    def __post_init__(self) -> None:
        if not self.name:
            raise InvalidROIConfigError("CountingLine.name is required")
        if self.start == self.end:
            raise InvalidROIConfigError(
                f"CountingLine '{self.name}' has zero length"
            )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start": list(self.start),
            "end": list(self.end),
            "direction": self.direction.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CountingLine":
        return cls(
            name=data["name"],
            start=(int(data["start"][0]), int(data["start"][1])),
            end=(int(data["end"][0]), int(data["end"][1])),
            direction=LineDirection(data.get("direction", "both")),
        )
