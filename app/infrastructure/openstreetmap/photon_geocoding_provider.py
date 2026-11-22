"""GeocodingProvider con Photon (komoot), un geocoder de OpenStreetMap pensado para
buscar mientras se escribe. Solo se usa al crear viajes, nunca en el pipeline.

La instancia pública (photon.komoot.io) es para uso liviano; el frontend ya espera
650 ms entre teclas. En producción se puede apuntar PHOTON_BASE_URL a una
instancia propia o pasar a Mapbox.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.modules.trips.application.ports.geocoding_provider import GeocodingResult
from app.shared.application.errors import ExternalServiceUnavailableError
from app.shared.domain.geo_point import GeoPoint

logger = logging.getLogger("cargo.geocoding")


def _display_name(properties: dict[str, Any]) -> str:
    street = properties.get("street")
    number = properties.get("housenumber")
    name = properties.get("name")
    first = " ".join(part for part in (street, number) if part) if street else None
    parts = [
        name,
        first if first and first != name else None,
        properties.get("district"),
        properties.get("city"),
        properties.get("state"),
        properties.get("country"),
    ]
    unique: list[str] = []
    for part in parts:
        if part and part not in unique:
            unique.append(str(part))
    return ", ".join(unique)


def _to_result(feature: dict[str, Any]) -> GeocodingResult:
    properties = feature.get("properties", {})
    longitude, latitude = feature["geometry"]["coordinates"]
    osm_id = properties.get("osm_id")
    return GeocodingResult(
        id=f"{properties.get('osm_type', '')}{osm_id}" if osm_id else f"{latitude},{longitude}",
        display_name=_display_name(properties) or f"{latitude:.6f}, {longitude:.6f}",
        latitude=float(latitude),
        longitude=float(longitude),
        category=properties.get("osm_key"),
        result_type=properties.get("type"),
    )


class PhotonGeocodingProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        user_agent: str,
        bias: GeoPoint | None = None,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._headers = {"User-Agent": user_agent}
        self._bias = bias

    async def search(self, query: str, limit: int) -> list[GeocodingResult]:
        params: dict[str, str] = {"q": query, "limit": str(limit)}
        if self._bias is not None:
            params.update(lat=str(self._bias.latitude), lon=str(self._bias.longitude))
        body = await self._get("/api/", params)
        return [_to_result(feature) for feature in body.get("features", [])]

    async def reverse(self, point: GeoPoint) -> GeocodingResult:
        body = await self._get("/reverse", {"lat": str(point.latitude), "lon": str(point.longitude)})
        features = body.get("features", [])
        if not features:
            return GeocodingResult(
                id=f"{point.latitude},{point.longitude}",
                display_name=f"{point.latitude:.6f}, {point.longitude:.6f}",
                latitude=point.latitude,
                longitude=point.longitude,
            )
        # Dejamos el punto exacto donde hizo clic; del geocoder solo tomamos el texto.
        result = _to_result(features[0])
        return GeocodingResult(
            id=result.id,
            display_name=result.display_name,
            latitude=point.latitude,
            longitude=point.longitude,
            category=result.category,
            result_type=result.result_type,
        )

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self._client.get(f"{self._base_url}{path}", params=params, headers=self._headers)
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            return body
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("photon geocoding failed", extra={"error": type(error).__name__})
            raise ExternalServiceUnavailableError("El servicio de direcciones no respondió.") from error
