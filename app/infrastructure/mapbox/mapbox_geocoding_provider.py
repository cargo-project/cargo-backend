"""GeocodingProvider con la API de Geocoding v6 de Mapbox."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.modules.trips.application.ports.geocoding_provider import GeocodingResult
from app.shared.application.errors import ExternalServiceUnavailableError
from app.shared.domain.geo_point import GeoPoint

logger = logging.getLogger("cargo.mapbox")


def _to_result(feature: dict[str, Any]) -> GeocodingResult:
    properties = feature.get("properties", {})
    longitude, latitude = feature["geometry"]["coordinates"]
    return GeocodingResult(
        id=str(properties.get("mapbox_id") or feature.get("id") or f"{latitude},{longitude}"),
        display_name=str(properties.get("full_address") or properties.get("name") or ""),
        latitude=float(latitude),
        longitude=float(longitude),
        category=properties.get("feature_type"),
        result_type=properties.get("feature_type"),
    )


class MapboxGeocodingProvider:
    def __init__(self, client: httpx.AsyncClient, token: str | None, api_base: str) -> None:
        self._client = client
        self._token = token
        self._api_base = api_base.rstrip("/")

    async def search(self, query: str, limit: int) -> list[GeocodingResult]:
        body = await self._get("/search/geocode/v6/forward", {"q": query, "limit": str(limit)})
        return [_to_result(feature) for feature in body.get("features", [])]

    async def reverse(self, point: GeoPoint) -> GeocodingResult:
        body = await self._get(
            "/search/geocode/v6/reverse",
            {"longitude": str(point.longitude), "latitude": str(point.latitude), "limit": "1"},
        )
        features = body.get("features", [])
        if not features:
            return GeocodingResult(
                id=f"{point.latitude},{point.longitude}",
                display_name=f"{point.latitude:.6f}, {point.longitude:.6f}",
                latitude=point.latitude,
                longitude=point.longitude,
            )
        return _to_result(features[0])

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self._token:
            raise ExternalServiceUnavailableError("Mapbox no está configurado (MAPBOX_TOKEN).")
        try:
            response = await self._client.get(
                f"{self._api_base}{path}",
                params={**params, "language": "es", "access_token": self._token},
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            return body
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("mapbox geocoding failed", extra={"error": type(error).__name__})
            raise ExternalServiceUnavailableError("El servicio de geocodificación no respondió.") from error
