from __future__ import annotations

import uuid
from typing import Protocol

from app.modules.trips.domain.entities.client import Client
from app.modules.trips.domain.entities.geofence import Geofence
from app.modules.trips.domain.entities.trip import Trip
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration


class TripRepository(Protocol):
    async def get_by_id(self, trip_id: uuid.UUID) -> Trip | None: ...

    async def get_by_code(self, code: str) -> Trip | None: ...

    async def code_exists(self, code: str) -> bool: ...

    async def list_ongoing(self) -> list[Trip]: ...

    async def add(self, trip: Trip) -> None: ...

    async def save(self, trip: Trip) -> None:
        """Guarda los cambios; lanza InvalidTripStateError si otro proceso lo modificó a la vez."""
        ...


class ClientRepository(Protocol):
    async def get_by_id(self, client_id: uuid.UUID) -> Client | None: ...

    async def list_all(self) -> list[Client]: ...

    async def add(self, client: Client) -> None: ...


class GeofenceRepository(Protocol):
    async def code_exists(self, code: str) -> bool: ...

    async def list_zones(self) -> list[Geofence]: ...

    async def add(self, geofence: Geofence) -> None: ...


class MonitoringDefaultsRepository(Protocol):
    """Configuración por defecto para los viajes nuevos (se edita en Configuración)."""

    async def get(self) -> MonitoringConfiguration: ...

    async def save(self, configuration: MonitoringConfiguration) -> None: ...
