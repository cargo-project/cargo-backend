"""Puertos que el contexto de monitoreo necesita del mundo exterior."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Protocol

from app.modules.monitoring.application.dto.monitoring_dto import (
    DashboardCounters,
    DashboardVehicleRow,
    MonitoringEventView,
    RecentActivity,
    TelemetryView,
    TrackView,
    TripSummary,
)
from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent
from app.modules.monitoring.domain.services.telemetry_acceptance_policy import TelemetryTripContext
from app.modules.monitoring.domain.value_objects.spatial_context import SpatialContext


class TelemetryContextProvider(Protocol):
    async def load(self, *, device_code: str, trip_id: uuid.UUID) -> TelemetryTripContext | None:
        """Devuelve None si el código de dispositivo no existe."""
        ...


class DeviceConnectionRecorder(Protocol):
    async def record(self, device_id: uuid.UUID, at: datetime) -> None: ...


class SpatialContextAnalyzer(Protocol):
    """Se implementa con PostGIS: distancia al destino, alejamiento, zona de llegada y desplazamiento."""

    async def analyze(self, telemetry: TelemetryEvent) -> SpatialContext: ...


class MonitoringTripDirectory(Protocol):
    async def describe(self, trip_id: uuid.UUID) -> TripSummary | None: ...


class MonitoringReadModel(Protocol):
    async def list_events(
        self, *, trip_code: str | None, status: str | None, event_type: str | None, limit: int
    ) -> list[MonitoringEventView]: ...

    async def get_event(self, event_id: uuid.UUID) -> MonitoringEventView | None: ...

    async def track(self, trip_code: str) -> TrackView | None: ...

    async def telemetry(self, trip_code: str, *, limit: int, before: datetime | None) -> list[TelemetryView]: ...

    async def dashboard_rows(self) -> list[DashboardVehicleRow]: ...

    async def dashboard_counters(self, *, now: datetime, online_window: timedelta) -> DashboardCounters: ...

    async def recent_activity(self, limit: int) -> list[RecentActivity]: ...
