from __future__ import annotations

from dataclasses import dataclass

from src.domain.exceptions import InvalidVehicleTypeError


@dataclass(frozen=True)
class VehicleType:
    name: str
    pce: float

    def __post_init__(self) -> None:
        if not self.name:
            raise InvalidVehicleTypeError("VehicleType.name is required")
        if self.pce <= 0:
            raise InvalidVehicleTypeError(
                f"VehicleType '{self.name}' must have pce > 0, got {self.pce}"
            )

    def to_dict(self) -> dict:
        return {"name": self.name, "pce": self.pce}

    @classmethod
    def from_dict(cls, data: dict) -> "VehicleType":
        return cls(name=data["name"], pce=float(data["pce"]))


COCO_TO_VEHICLE_TYPE: dict[int, VehicleType] = {
    2: VehicleType("car", pce=1.0),
    3: VehicleType("motorcycle", pce=0.3),
    5: VehicleType("bus", pce=3.0),
    7: VehicleType("truck", pce=2.5),
}

VEHICLE_CLASS_IDS: frozenset[int] = frozenset(COCO_TO_VEHICLE_TYPE.keys())


_NAME_TO_COCO_ID: dict[str, int] = {v.name: cid for cid, v in COCO_TO_VEHICLE_TYPE.items()}


def apply_pce_overrides(pce: dict[str, float]) -> None:
    """Replace PCE values in ``COCO_TO_VEHICLE_TYPE`` from a config mapping.

    Idempotent — call once at startup right after loading the YAML config.
    Only known vehicle names are accepted; unknown names raise to surface typos.
    """
    for name, value in pce.items():
        coco_id = _NAME_TO_COCO_ID.get(name)
        if coco_id is None:
            raise ValueError(
                f"vehicle_pce chứa tên xe không hợp lệ: {name!r}. "
                f"Hợp lệ: {sorted(_NAME_TO_COCO_ID)}"
            )
        COCO_TO_VEHICLE_TYPE[coco_id] = VehicleType(name=name, pce=float(value))
