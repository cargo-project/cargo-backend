from __future__ import annotations

import uuid

from app.modules.trips.domain.entities.geofence import Geofence
from app.modules.trips.domain.exceptions.trip_errors import InvalidGeofenceError
from app.modules.trips.domain.repositories.trip_repositories import GeofenceRepository
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.geo_point import GeoPoint


class ListGeofencesUseCase:
    def __init__(self, geofences: GeofenceRepository) -> None:
        self._geofences = geofences

    async def execute(self) -> list[Geofence]:
        return await self._geofences.list_zones()


class CreateGeofenceUseCase:
    def __init__(self, geofences: GeofenceRepository, uow: UnitOfWork, clock: Clock, audit: AuditLog) -> None:
        self._geofences = geofences
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, *, code: str, name: str, boundary: list[GeoPoint], actor_id: uuid.UUID) -> Geofence:
        geofence = Geofence.define_zone(code=code, name=name, boundary=boundary, now=self._clock.now())
        if await self._geofences.code_exists(geofence.code):
            raise InvalidGeofenceError(f"Ya existe la geocerca {geofence.code}.")
        await self._geofences.add(geofence)
        await self._audit.record(
            action="geofence.created", entity_type="geofence", entity_id=geofence.code, actor_id=actor_id
        )
        await self._uow.commit()
        return geofence
