"""Casos de uso que mueven el viaje por su ciclo de vida y lo anuncian al pipeline."""

from __future__ import annotations

import logging
import uuid

from app.modules.trips.application.ports.fleet_allocation import FleetAllocationPort
from app.modules.trips.application.trip_integration_events import (
    trip_config_updated_event,
    trip_ended_event,
    trip_started_event,
)
from app.modules.trips.domain.entities.trip import Trip
from app.modules.trips.domain.exceptions.trip_errors import TripNotFoundError
from app.modules.trips.domain.repositories.trip_repositories import TripRepository
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration
from app.modules.trips.domain.value_objects.trip_status import TripStatus
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.event_publisher import EventPublisher
from app.shared.application.unit_of_work import UnitOfWork

logger = logging.getLogger("cargo.trips")


class _TripCommand:
    def __init__(
        self,
        trips: TripRepository,
        publisher: EventPublisher,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        self._trips = trips
        self._publisher = publisher
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def _load(self, code: str) -> Trip:
        trip = await self._trips.get_by_code(code.upper())
        if trip is None:
            raise TripNotFoundError(f"No existe el viaje {code}.")
        return trip


class StartTripUseCase(_TripCommand):
    """Reserva vehículo + conductor, inicia el viaje y publica trip/started, todo junto.

    CEP empieza a monitorear cuando recibe trip/started; el dispositivo se entera de su
    viaje activo por el mensaje retenido en devices/{code}/trip.
    """

    def __init__(
        self,
        trips: TripRepository,
        fleet: FleetAllocationPort,
        publisher: EventPublisher,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        super().__init__(trips, publisher, uow, clock, audit)
        self._fleet = fleet

    async def execute(self, code: str, *, actor_id: uuid.UUID | None) -> str:
        trip = await self._load(code)
        trip.ensure_can_start()  # falla rápido antes de reservar recursos de la flota
        now = self._clock.now()
        device_id = await self._fleet.allocate(
            trip_id=trip.id, vehicle_id=trip.vehicle_id, driver_id=trip.driver_id, now=now
        )
        trip.start(now=now, device_id=device_id)
        await self._trips.save(trip)
        await self._publisher.publish(trip_started_event(trip, occurred_at=now))
        await self._audit.record(action="trip.started", entity_type="trip", entity_id=trip.code, actor_id=actor_id)
        await self._uow.commit()
        logger.info("trip started", extra={"trip": trip.code})
        return trip.code


class FinishTripUseCase(_TripCommand):
    """Termina un viaje (a mano o cuando se confirma DESTINATION_ARRIVAL)."""

    def __init__(
        self,
        trips: TripRepository,
        fleet: FleetAllocationPort,
        publisher: EventPublisher,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        super().__init__(trips, publisher, uow, clock, audit)
        self._fleet = fleet

    async def execute(self, code: str, *, actor_id: uuid.UUID | None, reason: str = "manual") -> str:
        trip = await self._load(code)
        await self._finish(trip, actor_id=actor_id, reason=reason)
        return trip.code

    async def finish_on_arrival(self, trip_id: uuid.UUID) -> bool:
        """Versión idempotente que dispara CEP: si la llegada se reentrega, no hace nada."""
        trip = await self._trips.get_by_id(trip_id)
        if trip is None or trip.status != TripStatus.ONGOING:
            return False
        await self._finish(trip, actor_id=None, reason="destination_arrival")
        return True

    async def _finish(self, trip: Trip, *, actor_id: uuid.UUID | None, reason: str) -> None:
        now = self._clock.now()
        trip.finish(now=now, reason=reason)
        await self._fleet.release(trip_id=trip.id, vehicle_id=trip.vehicle_id, driver_id=trip.driver_id, now=now)
        await self._trips.save(trip)
        await self._publisher.publish(trip_ended_event(trip, occurred_at=now))
        await self._audit.record(
            action="trip.finished",
            entity_type="trip",
            entity_id=trip.code,
            actor_id=actor_id,
            details={"reason": reason},
        )
        await self._uow.commit()
        logger.info("trip finished", extra={"trip": trip.code, "reason": reason})


class CancelTripUseCase(_TripCommand):
    def __init__(
        self,
        trips: TripRepository,
        fleet: FleetAllocationPort,
        publisher: EventPublisher,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        super().__init__(trips, publisher, uow, clock, audit)
        self._fleet = fleet

    async def execute(self, code: str, *, actor_id: uuid.UUID | None) -> str:
        trip = await self._load(code)
        was_ongoing = trip.status == TripStatus.ONGOING
        now = self._clock.now()
        trip.cancel(now=now)
        if was_ongoing:
            await self._fleet.release(trip_id=trip.id, vehicle_id=trip.vehicle_id, driver_id=trip.driver_id, now=now)
        await self._trips.save(trip)
        if was_ongoing:
            await self._publisher.publish(trip_ended_event(trip, occurred_at=now))
        await self._audit.record(action="trip.cancelled", entity_type="trip", entity_id=trip.code, actor_id=actor_id)
        await self._uow.commit()
        return trip.code


class UpdateMonitoringConfigurationUseCase(_TripCommand):
    """Cambia los umbrales de un viaje; si está en curso se reanuncia con trip/config-updated."""

    async def execute(self, code: str, changes: dict[str, float | int], *, actor_id: uuid.UUID | None) -> str:
        trip = await self._load(code)
        new_configuration: MonitoringConfiguration = trip.monitoring_configuration.with_changes(**changes)
        trip.update_monitoring_configuration(new_configuration)
        await self._trips.save(trip)
        if trip.is_monitored:
            await self._publisher.publish(trip_config_updated_event(trip, occurred_at=self._clock.now()))
        await self._audit.record(
            action="trip.monitoring_config_changed",
            entity_type="trip",
            entity_id=trip.code,
            actor_id=actor_id,
            details={"changes": changes},
        )
        await self._uow.commit()
        return trip.code


class ReannounceActiveTripsUseCase:
    """Resincronización periódica: vuelve a publicar trip/started de cada viaje en curso.

    Siddhi guarda el estado de cada viaje en memoria; si CEP se reinicia, con esto
    recupera los viajes que tiene que vigilar sin llamar nunca a la API. Para CEP es un upsert.
    """

    def __init__(self, trips: TripRepository, publisher: EventPublisher, uow: UnitOfWork, clock: Clock) -> None:
        self._trips = trips
        self._publisher = publisher
        self._uow = uow
        self._clock = clock

    async def execute(self) -> int:
        ongoing = await self._trips.list_ongoing()
        now = self._clock.now()
        for trip in ongoing:
            await self._publisher.publish(trip_started_event(trip, occurred_at=now))
        await self._uow.commit()
        return len(ongoing)
