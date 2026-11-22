from __future__ import annotations

from dataclasses import dataclass

from app.modules.trips.domain.exceptions.trip_errors import InvalidTripError
from app.shared.domain.geo_point import GeoPoint


@dataclass(frozen=True, slots=True)
class Location:
    """Punto con nombre que se usa como origen o destino del viaje."""

    label: str
    point: GeoPoint

    def __post_init__(self) -> None:
        label = " ".join(self.label.split())
        if not 1 <= len(label) <= 300:
            raise InvalidTripError("La dirección debe tener entre 1 y 300 caracteres.")
        object.__setattr__(self, "label", label)
