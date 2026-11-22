"""Puerto de consultas para las pantallas de flota.

Los listados necesitan datos de otros contextos (viaje actual, conductor a bordo).
Cargar varios agregados por fila sería un desperdicio, así que hay un read model
aparte para estas consultas. Es solo lectura, nunca cambia estado.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.modules.fleet.application.dto.fleet_dto import DriverView, VehicleView


@dataclass(frozen=True, slots=True)
class DeviceRow:
    id: uuid.UUID
    code: str
    device_type: str
    serial_number: str
    firmware_version: str
    vehicle_code: str | None
    is_active: bool
    last_connection_at: datetime | None


class FleetReadModel(Protocol):
    async def list_vehicles(self) -> list[VehicleView]: ...

    async def get_vehicle(self, code: str) -> VehicleView | None: ...

    async def list_drivers(self) -> list[DriverView]: ...

    async def get_driver(self, code: str) -> DriverView | None: ...

    async def list_devices(self) -> list[DeviceRow]: ...

    async def get_device(self, code: str) -> DeviceRow | None: ...
