from __future__ import annotations

from app.modules.trips.application.ports.geocoding_provider import GeocodingProvider, GeocodingResult
from app.shared.domain.geo_point import GeoPoint


class SearchLocationsUseCase:
    """Autocompletado de direcciones al crear un viaje."""

    def __init__(self, provider: GeocodingProvider) -> None:
        self._provider = provider

    async def execute(self, query: str, limit: int) -> list[GeocodingResult]:
        cleaned = " ".join(query.split())
        if len(cleaned) < 3:
            return []
        return await self._provider.search(cleaned, max(1, min(limit, 10)))


class ReverseGeocodeUseCase:
    def __init__(self, provider: GeocodingProvider) -> None:
        self._provider = provider

    async def execute(self, latitude: float, longitude: float) -> GeocodingResult:
        return await self._provider.reverse(GeoPoint(latitude, longitude))
