from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from app.modules.monitoring.application.dto.monitoring_dto import (
    DashboardVehicleView,
    DashboardView,
    MonitoringEventView,
    TelemetryView,
    TrackView,
)
from app.modules.monitoring.application.ports.monitoring_ports import MonitoringReadModel
from app.modules.monitoring.domain.exceptions.monitoring_errors import (
    MonitoringEventNotFoundError,
    UnknownTripError,
)
from app.modules.monitoring.domain.repositories.monitoring_repositories import MonitoringEventRepository
from app.modules.monitoring.domain.services.vehicle_situation_classifier import (
    VehicleSituationClassifier,
    VehicleSnapshot,
)
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


class GetMonitoringEventsUseCase:
    def __init__(self, read_model: MonitoringReadModel) -> None:
        self._read_model = read_model

    async def execute(
        self,
        *,
        trip_code: str | None = None,
        status: str | None = None,
        event_type: str | None = None,
        limit: int = 200,
    ) -> list[MonitoringEventView]:
        return await self._read_model.list_events(
            trip_code=trip_code.upper() if trip_code else None,
            status=status,
            event_type=event_type,
            limit=max(1, min(limit, 500)),
        )


class AcknowledgeMonitoringEventUseCase:
    """Marca un evento como revisado por un operador (queda quién y cuándo)."""

    def __init__(
        self,
        events: MonitoringEventRepository,
        read_model: MonitoringReadModel,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        self._events = events
        self._read_model = read_model
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, event_id: uuid.UUID, *, user_id: uuid.UUID) -> MonitoringEventView:
        event = await self._events.get(event_id)
        if event is None:
            raise MonitoringEventNotFoundError("El evento no existe.")
        event.acknowledge(user_id=user_id, now=self._clock.now())
        await self._events.save(event)
        await self._audit.record(
            action="monitoring_event.acknowledged",
            entity_type="monitoring_event",
            entity_id=str(event.id),
            actor_id=user_id,
            details={"type": event.event_type.value},
        )
        await self._uow.commit()
        view = await self._read_model.get_event(event_id)
        assert view is not None
        return view


class GetTripTrackUseCase:
    """Recorrido GNSS real del viaje (LIVE y DELAYED, ordenado por event_time)."""

    def __init__(self, read_model: MonitoringReadModel) -> None:
        self._read_model = read_model

    async def execute(self, trip_code: str) -> TrackView:
        track = await self._read_model.track(trip_code.upper())
        if track is None:
            raise UnknownTripError(f"No existe el viaje {trip_code}.")
        return track


class GetTripTelemetryUseCase:
    def __init__(self, read_model: MonitoringReadModel) -> None:
        self._read_model = read_model

    async def execute(self, trip_code: str, *, limit: int = 500, before: datetime | None = None) -> list[TelemetryView]:
        return await self._read_model.telemetry(trip_code.upper(), limit=max(1, min(limit, 5000)), before=before)


class GetDashboardUseCase:
    def __init__(
        self,
        read_model: MonitoringReadModel,
        clock: Clock,
        online_window: timedelta,
        classifier: VehicleSituationClassifier | None = None,
    ) -> None:
        self._read_model = read_model
        self._clock = clock
        self._online_window = online_window
        self._classifier = classifier or VehicleSituationClassifier()

    async def execute(self) -> DashboardView:
        now = self._clock.now()
        vehicles = []
        for row in await self._read_model.dashboard_rows():
            situation = self._classifier.classify(
                VehicleSnapshot(
                    has_pending_alert=row.has_pending_alert,
                    last_signal_at=row.last_signal_at,
                    speed_kmh=row.speed_kmh,
                    connection_loss_threshold=timedelta(seconds=row.connection_loss_seconds),
                    stop_speed_kmh=row.stop_speed_kmh,
                ),
                now,
            )
            vehicles.append(
                DashboardVehicleView(
                    vehicle_code=row.vehicle_code,
                    plate=row.plate,
                    driver_name=row.driver_name,
                    situation=situation.value,
                    speed_kmh=row.speed_kmh,
                    origin_label=row.origin_label,
                    destination_label=row.destination_label,
                    last_signal_at=row.last_signal_at,
                    latitude=row.latitude,
                    longitude=row.longitude,
                )
            )
        return DashboardView(
            counters=await self._read_model.dashboard_counters(now=now, online_window=self._online_window),
            vehicles=vehicles,
            recent_activity=await self._read_model.recent_activity(10),
        )
