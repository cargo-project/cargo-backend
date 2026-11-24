"""Eliminar vehículos, conductores y dispositivos.

Solo se borra lo que nunca se usó. Si el registro ya tiene viajes o telemetría, borrarlo dejaría
historial huérfano (viajes, alertas, recorridos), así que se rechaza y se sugiere desactivarlo.
"""

from __future__ import annotations

import uuid

from app.modules.fleet.domain.exceptions.fleet_errors import (
    DriverNotFoundError,
    FleetResourceInUseError,
    IoTDeviceNotFoundError,
    VehicleNotFoundError,
)
from app.modules.fleet.domain.repositories.fleet_repositories import (
    DriverRepository,
    FleetRemovalRepository,
    IoTDeviceRepository,
    VehicleRepository,
)
from app.shared.application.audit_log import AuditLog
from app.shared.application.unit_of_work import UnitOfWork


class DeleteVehicleUseCase:
    def __init__(
        self, vehicles: VehicleRepository, removal: FleetRemovalRepository, uow: UnitOfWork, audit: AuditLog
    ) -> None:
        self._vehicles = vehicles
        self._removal = removal
        self._uow = uow
        self._audit = audit

    async def execute(self, code: str, *, actor_id: uuid.UUID) -> None:
        vehicle = await self._vehicles.get_by_code(code.upper())
        if vehicle is None:
            raise VehicleNotFoundError(f"No existe el vehículo {code}.")
        trips = await self._removal.vehicle_trip_count(vehicle.id)
        if trips:
            raise FleetResourceInUseError(
                f"El vehículo {vehicle.code} tiene {trips} viaje(s) registrado(s); para conservar el historial "
                "no se puede eliminar. Puedes marcarlo como En mantenimiento o Sin conexión."
            )
        await self._removal.remove_vehicle(vehicle.id)
        await self._audit.record(
            action="vehicle.deleted",
            entity_type="vehicle",
            entity_id=vehicle.code,
            actor_id=actor_id,
            details={"plate": vehicle.plate},
        )
        await self._uow.commit()


class DeleteDriverUseCase:
    def __init__(
        self, drivers: DriverRepository, removal: FleetRemovalRepository, uow: UnitOfWork, audit: AuditLog
    ) -> None:
        self._drivers = drivers
        self._removal = removal
        self._uow = uow
        self._audit = audit

    async def execute(self, code: str, *, actor_id: uuid.UUID) -> None:
        driver = await self._drivers.get_by_code(code.upper())
        if driver is None:
            raise DriverNotFoundError(f"No existe el conductor {code}.")
        trips = await self._removal.driver_trip_count(driver.id)
        if trips:
            raise FleetResourceInUseError(
                f"{driver.full_name} tiene {trips} viaje(s) registrado(s); para conservar el historial "
                "no se puede eliminar. Puedes marcarlo como Inactivo."
            )
        await self._removal.remove_driver(driver.id)
        await self._audit.record(
            action="driver.deleted",
            entity_type="driver",
            entity_id=driver.code,
            actor_id=actor_id,
            details={"name": driver.full_name},
        )
        await self._uow.commit()


class DeleteDeviceUseCase:
    def __init__(
        self, devices: IoTDeviceRepository, removal: FleetRemovalRepository, uow: UnitOfWork, audit: AuditLog
    ) -> None:
        self._devices = devices
        self._removal = removal
        self._uow = uow
        self._audit = audit

    async def execute(self, code: str, *, actor_id: uuid.UUID) -> None:
        device = await self._devices.get_by_code(code.upper())
        if device is None:
            raise IoTDeviceNotFoundError(f"No existe el dispositivo {code}.")
        if await self._removal.device_history_count(device.id):
            raise FleetResourceInUseError(
                f"El dispositivo {device.code} ya envió telemetría o está ligado a viajes; para conservar el "
                "historial no se puede eliminar. Puedes desactivarlo."
            )
        await self._removal.remove_device(device.id)
        await self._audit.record(
            action="device.deleted", entity_type="device", entity_id=device.code, actor_id=actor_id
        )
        await self._uow.commit()
