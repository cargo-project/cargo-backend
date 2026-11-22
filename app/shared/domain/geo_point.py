"""Coordenada WGS84 como value object (SRID 4326)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.shared.domain.errors import BusinessRuleViolationError


class InvalidCoordinatesError(BusinessRuleViolationError):
    code = "invalid_coordinates"


@dataclass(frozen=True, slots=True)
class GeoPoint:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.latitude) and math.isfinite(self.longitude)):
            raise InvalidCoordinatesError("Las coordenadas deben ser números finitos.")
        if not -90.0 <= self.latitude <= 90.0:
            raise InvalidCoordinatesError("La latitud debe estar entre -90 y 90.", details={"latitude": self.latitude})
        if not -180.0 <= self.longitude <= 180.0:
            raise InvalidCoordinatesError(
                "La longitud debe estar entre -180 y 180.", details={"longitude": self.longitude}
            )

    def as_lon_lat(self) -> tuple[float, float]:
        """Orden de ejes de GeoJSON / PostGIS (lon, lat)."""
        return (self.longitude, self.latitude)

    def approximate_distance_m(self, other: GeoPoint) -> float:
        """Distancia haversine. Solo para chequeos gruesos del dominio (ej. origen != destino);
        el análisis espacial de verdad lo hace PostGIS.
        """
        radius = 6_371_008.8
        lat1, lat2 = math.radians(self.latitude), math.radians(other.latitude)
        dlat = lat2 - lat1
        dlon = math.radians(other.longitude - self.longitude)
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * radius * math.asin(math.sqrt(h))
