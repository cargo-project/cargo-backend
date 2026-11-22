from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PlanningResources:
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID


class FleetAllocationPort(Protocol):
    """Lo que viajes necesita del contexto de flota (puerto definido por quien lo usa).

    El adaptador trabaja dentro de la unit of work del que llama, así reservar el
    vehículo, el conductor e iniciar el viaje se confirman (o fallan) juntos.
    """

    async def resolve_for_planning(self, *, vehicle_code: str, driver_code: str) -> PlanningResources:
        """Lanza errores de no encontrado / no disponible si no se pueden planificar los recursos."""
        ...

    async def allocate(
        self, *, trip_id: uuid.UUID, vehicle_id: uuid.UUID, driver_id: uuid.UUID, now: datetime
    ) -> uuid.UUID:
        """Pone el vehículo en ruta y el conductor asignado; devuelve el id del gateway de telemetría."""
        ...

    async def release(
        self, *, trip_id: uuid.UUID, vehicle_id: uuid.UUID, driver_id: uuid.UUID, now: datetime
    ) -> None: ...
