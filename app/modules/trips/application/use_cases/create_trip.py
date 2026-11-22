from __future__ import annotations

import secrets
import uuid

from app.modules.trips.application.dto.trip_dto import CreateTripCommand
from app.modules.trips.application.ports.fleet_allocation import FleetAllocationPort
from app.modules.trips.application.ports.recipient_directory import RecipientDirectory
from app.modules.trips.domain.entities.trip import Trip
from app.modules.trips.domain.exceptions.trip_errors import ClientNotFoundError, InvalidTripError
from app.modules.trips.domain.repositories.trip_repositories import (
    ClientRepository,
    MonitoringDefaultsRepository,
    TripRepository,
)
from app.modules.trips.domain.value_objects.location import Location
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.geo_point import GeoPoint


class CreateTripUseCase:
    """Planifica un viaje: valida recursos y destinatarios y copia la configuración de
    monitoreo por defecto. El viaje arranca después (StartTripUseCase).

    No se propone ni se guarda ninguna ruta: un viaje es origen + destino, y lo que se
    ve en el mapa es lo que el vehículo realmente recorrió (su telemetría).

    Acá solo se revisa que vehículo y conductor estén disponibles; se reservan al
    iniciar, que es cuando de verdad empieza la operación.
    """

    def __init__(
        self,
        trips: TripRepository,
        clients: ClientRepository,
        defaults: MonitoringDefaultsRepository,
        fleet: FleetAllocationPort,
        recipients: RecipientDirectory,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        self._trips = trips
        self._clients = clients
        self._defaults = defaults
        self._fleet = fleet
        self._recipients = recipients
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, command: CreateTripCommand, *, actor_id: uuid.UUID) -> str:
        origin = Location(command.origin_label, GeoPoint(command.origin_latitude, command.origin_longitude))
        destination = Location(
            command.destination_label,
            GeoPoint(command.destination_latitude, command.destination_longitude),
        )
        resources = await self._fleet.resolve_for_planning(
            vehicle_code=command.vehicle_code.upper(), driver_code=command.driver_code.upper()
        )
        invalid = await self._recipients.find_missing_or_inactive(command.recipient_ids)
        if invalid:
            raise InvalidTripError(
                "Hay destinatarios inexistentes o inactivos.",
                details={"recipientIds": sorted(str(item) for item in invalid)},
            )
        if command.client_id and await self._clients.get_by_id(command.client_id) is None:
            raise ClientNotFoundError("El cliente indicado no existe.")

        trip = Trip.plan(
            code=await self._new_code(),
            vehicle_id=resources.vehicle_id,
            driver_id=resources.driver_id,
            origin=origin,
            destination=destination,
            cargo_description=command.cargo_description,
            monitoring_configuration=await self._defaults.get(),
            recipient_ids=command.recipient_ids,
            now=self._clock.now(),
            created_by=actor_id,
            client_id=command.client_id,
            planned_start_at=command.planned_start_at,
        )
        await self._trips.add(trip)
        await self._audit.record(action="trip.created", entity_type="trip", entity_id=trip.code, actor_id=actor_id)
        await self._uow.commit()
        return trip.code

    async def _new_code(self) -> str:
        day = self._clock.now().strftime("%y%m%d")
        while True:
            candidate = f"TRP-{day}-{secrets.token_hex(2).upper()}"
            if not await self._trips.code_exists(candidate):
                return candidate
