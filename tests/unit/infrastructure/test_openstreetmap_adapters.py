"""Adaptador de geocodificación Photon (OpenStreetMap) con transportes simulados (sin red)."""

from __future__ import annotations

import httpx
import pytest

from app.infrastructure.openstreetmap.photon_geocoding_provider import PhotonGeocodingProvider
from app.shared.application.errors import ExternalServiceUnavailableError
from app.shared.domain.geo_point import GeoPoint

PHOTON_FEATURE = {
    "geometry": {"coordinates": [-76.9966754, -12.0867473]},
    "properties": {
        "osm_type": "W",
        "osm_id": 1367095086,
        "osm_key": "highway",
        "type": "street",
        "name": "Avenida Javier Prado Este",
        "city": "San Borja",
        "state": "Lima",
        "country": "Perú",
    },
}


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_photon_search_builds_readable_address_with_location_bias() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"features": [PHOTON_FEATURE]})

    provider = PhotonGeocodingProvider(
        _client(httpx.MockTransport(handle)), "https://photon.test", "ua", GeoPoint(-12.0464, -77.0428)
    )
    results = await provider.search("javier prado", 5)
    assert results[0].display_name == "Avenida Javier Prado Este, San Borja, Lima, Perú"
    assert results[0].latitude == -12.0867473 and results[0].id == "W1367095086"
    assert seen[0].url.params["lat"] == "-12.0464" and seen[0].url.params["limit"] == "5"
    assert seen[0].headers["user-agent"] == "ua"


async def test_photon_reverse_keeps_clicked_point() -> None:
    body = {
        "features": [
            {
                "geometry": {"coordinates": [-77.0429, -12.0465]},
                "properties": {
                    "name": "Metropolitano",
                    "street": "Avenida Alfonso Ugarte",
                    "city": "Lima",
                    "country": "Perú",
                },
            }
        ]
    }
    provider = PhotonGeocodingProvider(
        _client(httpx.MockTransport(lambda _: httpx.Response(200, json=body))), "https://photon.test", "ua"
    )
    result = await provider.reverse(GeoPoint(-12.0464, -77.0428))
    assert result.display_name == "Metropolitano, Avenida Alfonso Ugarte, Lima, Perú"
    assert (result.latitude, result.longitude) == (-12.0464, -77.0428)


async def test_photon_failure_is_unavailable() -> None:
    provider = PhotonGeocodingProvider(_client(httpx.MockTransport(lambda _: httpx.Response(502))), "https://p", "ua")
    with pytest.raises(ExternalServiceUnavailableError):
        await provider.search("lima", 5)
