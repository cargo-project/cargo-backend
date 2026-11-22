"""Historial de asignaciones (qué se emparejó con qué y cuándo)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.shared.domain.entity import Entity


@dataclass(eq=False)
class VehicleDeviceAssignment(Entity):
    id: uuid.UUID
    vehicle_id: uuid.UUID
    device_id: uuid.UUID
    assigned_at: datetime
    released_at: datetime | None = None

    @classmethod
    def open(cls, *, vehicle_id: uuid.UUID, device_id: uuid.UUID, now: datetime) -> VehicleDeviceAssignment:
        return cls(id=uuid.uuid4(), vehicle_id=vehicle_id, device_id=device_id, assigned_at=now)

    def release(self, now: datetime) -> None:
        if self.released_at is None:
            self.released_at = now


@dataclass(eq=False)
class VehicleDriverAssignment(Entity):
    """Se crea al iniciar el viaje y se libera al terminar; trip_id guarda el contexto."""

    id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    trip_id: uuid.UUID
    assigned_at: datetime
    released_at: datetime | None = None

    @classmethod
    def open(
        cls, *, vehicle_id: uuid.UUID, driver_id: uuid.UUID, trip_id: uuid.UUID, now: datetime
    ) -> VehicleDriverAssignment:
        return cls(id=uuid.uuid4(), vehicle_id=vehicle_id, driver_id=driver_id, trip_id=trip_id, assigned_at=now)

    def release(self, now: datetime) -> None:
        if self.released_at is None:
            self.released_at = now
