from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.composition import trips_factory
from app.core.http.dependencies import ScopeDep
from app.core.http.envelope import ERROR_RESPONSES, DataEnvelope, wrap
from app.modules.identity.presentation.api.auth_dependencies import AdminUser, CurrentUser
from app.modules.trips.presentation.schemas.trip_schemas import (
    ClientRequest,
    ClientResponse,
    CreateTripRequest,
    GeocodingResultResponse,
    GeofenceRequest,
    GeofenceResponse,
    MonitoringConfigPatch,
    TripResponse,
)
from app.shared.domain.geo_point import GeoPoint

trips_router = APIRouter(prefix="/trips", tags=["trips"], responses=ERROR_RESPONSES)
clients_router = APIRouter(prefix="/clients", tags=["clients"], responses=ERROR_RESPONSES)
geofences_router = APIRouter(prefix="/geofences", tags=["geofences"], responses=ERROR_RESPONSES)
geocoding_router = APIRouter(prefix="/geocoding", tags=["geocoding"], responses=ERROR_RESPONSES)


async def _trip_response(scope: ScopeDep, code: str) -> DataEnvelope[TripResponse]:
    return wrap(TripResponse.from_view(await trips_factory.get_trip(scope).execute(code)))


@trips_router.get("", summary="List trips (newest first)")
async def list_trips(_: CurrentUser, scope: ScopeDep) -> DataEnvelope[list[TripResponse]]:
    views = await trips_factory.list_trips(scope).execute()
    return wrap([TripResponse.from_view(view) for view in views])


@trips_router.post("", status_code=status.HTTP_201_CREATED, summary="Plan a trip (status: configured)")
async def create_trip(body: CreateTripRequest, user: CurrentUser, scope: ScopeDep) -> DataEnvelope[TripResponse]:
    code = await trips_factory.create_trip(scope).execute(body.to_command(), actor_id=user.id)
    return await _trip_response(scope, code)


@trips_router.get("/{code}", summary="Trip detail")
async def get_trip(code: str, _: CurrentUser, scope: ScopeDep) -> DataEnvelope[TripResponse]:
    return await _trip_response(scope, code)


@trips_router.post("/{code}/start", summary="Start the trip; CEP monitoring begins (trip/started)")
async def start_trip(code: str, user: CurrentUser, scope: ScopeDep) -> DataEnvelope[TripResponse]:
    await trips_factory.start_trip(scope).execute(code, actor_id=user.id)
    return await _trip_response(scope, code)


@trips_router.post("/{code}/finish", summary="Finish the trip (trip/ended)")
async def finish_trip(code: str, user: CurrentUser, scope: ScopeDep) -> DataEnvelope[TripResponse]:
    await trips_factory.finish_trip(scope).execute(code, actor_id=user.id)
    return await _trip_response(scope, code)


@trips_router.post("/{code}/cancel", summary="Cancel a configured or ongoing trip")
async def cancel_trip(code: str, user: CurrentUser, scope: ScopeDep) -> DataEnvelope[TripResponse]:
    await trips_factory.cancel_trip(scope).execute(code, actor_id=user.id)
    return await _trip_response(scope, code)


@trips_router.patch("/{code}/monitoring-config", summary="Change per-trip thresholds (ADMIN)")
async def update_monitoring_config(
    code: str, body: MonitoringConfigPatch, admin: AdminUser, scope: ScopeDep
) -> DataEnvelope[TripResponse]:
    await trips_factory.update_monitoring_configuration(scope).execute(code, body.changes(), actor_id=admin.id)
    return await _trip_response(scope, code)


@clients_router.get("", summary="List clients")
async def list_clients(_: CurrentUser, scope: ScopeDep) -> DataEnvelope[list[ClientResponse]]:
    return wrap([ClientResponse.from_entity(c) for c in await trips_factory.list_clients(scope).execute()])


@clients_router.post("", status_code=status.HTTP_201_CREATED, summary="Register a client")
async def create_client(body: ClientRequest, user: CurrentUser, scope: ScopeDep) -> DataEnvelope[ClientResponse]:
    client = await trips_factory.create_client(scope).execute(
        name=body.name, tax_id=body.tax_id, contact_email=body.contact_email, actor_id=user.id
    )
    return wrap(ClientResponse.from_entity(client))


@geofences_router.get("", summary="List operator-defined zones")
async def list_geofences(_: CurrentUser, scope: ScopeDep) -> DataEnvelope[list[GeofenceResponse]]:
    return wrap([GeofenceResponse.from_entity(g) for g in await trips_factory.list_geofences(scope).execute()])


@geofences_router.post("", status_code=status.HTTP_201_CREATED, summary="Create a zone (ADMIN)")
async def create_geofence(body: GeofenceRequest, admin: AdminUser, scope: ScopeDep) -> DataEnvelope[GeofenceResponse]:
    geofence = await trips_factory.create_geofence(scope).execute(
        code=body.code,
        name=body.name,
        boundary=[GeoPoint(p.latitude, p.longitude) for p in body.boundary],
        actor_id=admin.id,
    )
    return wrap(GeofenceResponse.from_entity(geofence))


@geocoding_router.get("/search", summary="Address autocomplete (Mapbox)")
async def search_locations(
    _: CurrentUser,
    scope: ScopeDep,
    query: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> DataEnvelope[list[GeocodingResultResponse]]:
    results = await trips_factory.search_locations(scope).execute(query, limit)
    return wrap([GeocodingResultResponse.model_validate(r) for r in results])


@geocoding_router.get("/reverse", summary="Reverse geocoding (Mapbox)")
async def reverse_geocode(
    _: CurrentUser,
    scope: ScopeDep,
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
) -> DataEnvelope[GeocodingResultResponse]:
    result = await trips_factory.reverse_geocode(scope).execute(latitude, longitude)
    return wrap(GeocodingResultResponse.model_validate(result))
