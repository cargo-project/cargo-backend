from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.shared.domain.geo_point import GeoPoint


@dataclass(frozen=True, slots=True)
class GeocodingResult:
    id: str
    display_name: str
    latitude: float
    longitude: float
    category: str | None = None
    result_type: str | None = None


class GeocodingProvider(Protocol):
    """Búsqueda de direcciones al crear un viaje (nunca en el pipeline de telemetría)."""

    async def search(self, query: str, limit: int) -> list[GeocodingResult]: ...

    async def reverse(self, point: GeoPoint) -> GeocodingResult: ...
