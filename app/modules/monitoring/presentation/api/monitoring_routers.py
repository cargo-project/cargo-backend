from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.composition import monitoring_factory
from app.core.http.dependencies import ScopeDep
from app.core.http.envelope import ERROR_RESPONSES, DataEnvelope, wrap
from app.modules.identity.presentation.api.auth_dependencies import CurrentUser
from app.modules.monitoring.presentation.schemas.monitoring_schemas import (
    DashboardResponse,
    MonitoringEventResponse,
    TelemetryResponse,
    TrackResponse,
)

monitoring_router = APIRouter(tags=["monitoring"], responses=ERROR_RESPONSES)

EventTypeFilter = Literal[
    "ROUTE_DEVIATION", "PROLONGED_STOP", "CONNECTION_LOSS", "DESTINATION_ARRIVAL", "EMERGENCY", "TRIP_STARTED"
]


@monitoring_router.get("/events", summary="Detected monitoring events (alerts), newest first")
async def list_events(
    _: CurrentUser,
    scope: ScopeDep,
    trip_code: Annotated[str | None, Query(max_length=32)] = None,
    status: Literal["pending", "reviewed"] | None = None,
    type: EventTypeFilter | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> DataEnvelope[list[MonitoringEventResponse]]:
    views = await monitoring_factory.get_monitoring_events(scope).execute(
        trip_code=trip_code, status=status, event_type=type, limit=limit
    )
    return wrap([MonitoringEventResponse.from_view(view) for view in views])


@monitoring_router.patch("/events/{event_id}/review", summary="Acknowledge (review) an event")
async def review_event(
    event_id: uuid.UUID, user: CurrentUser, scope: ScopeDep
) -> DataEnvelope[MonitoringEventResponse]:
    view = await monitoring_factory.acknowledge_monitoring_event(scope).execute(event_id, user_id=user.id)
    return wrap(MonitoringEventResponse.from_view(view))


@monitoring_router.get("/trips/{code}/track", summary="Actual GNSS path as GeoJSON LineString")
async def get_track(code: str, _: CurrentUser, scope: ScopeDep) -> DataEnvelope[TrackResponse]:
    return wrap(TrackResponse.from_view(await monitoring_factory.get_trip_track(scope).execute(code)))


@monitoring_router.get("/trips/{code}/telemetry", summary="Historical telemetry (LIVE + DELAYED)")
async def get_telemetry(
    code: str,
    _: CurrentUser,
    scope: ScopeDep,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    before: datetime | None = None,
) -> DataEnvelope[list[TelemetryResponse]]:
    views = await monitoring_factory.get_trip_telemetry(scope).execute(code, limit=limit, before=before)
    return wrap([TelemetryResponse.from_view(view) for view in views])


@monitoring_router.get("/dashboard", summary="Supervision-by-exception summary")
async def get_dashboard(_: CurrentUser, scope: ScopeDep) -> DataEnvelope[DashboardResponse]:
    return wrap(DashboardResponse.from_view(await monitoring_factory.get_dashboard(scope).execute()))
