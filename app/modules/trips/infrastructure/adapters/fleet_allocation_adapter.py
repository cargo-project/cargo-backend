"""Adaptador del FleetAllocationPort (que define viajes) sobre el dominio de flota.

Solo depende de las interfaces de repositorio y entidades del dominio de flota; los
repositorios concretos los inyecta la raíz de composición y comparten la sesión del que
llama, así la reserva de flota y el cambio del viaje se confirman juntos.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.modules.fleet.domain.entities.assignments import VehicleDriverAssignment
from app.modules.fleet.domain.exceptions.fleet_errors import (
    DriverNotFoundError,
    VehicleNotFoundError,
    VehicleWithoutDeviceError,
)
from app.modules.fleet.domain.repositories.fleet_repositories import (
    DriverAssignmentRepository,
    DriverRepository,
    IoTDeviceRepository,
    VehicleRepository,
)
from app.modules.trips.application.ports.fleet_allocation import PlanningResources


class FleetAllocationAdapter:
    def __init__(
        self,
        vehicles: VehicleRepository,
        drivers: DriverRepository,
        devices: IoTDeviceRepository,
        driver_assignments: DriverAssignmentRepository,
    ) -> None:
        self._vehicles = vehicles
        self._drivers = drivers
        self._devices = devices
        self._driver_assignments = driver_assignments

    async def resolve_for_planning(self, *, vehicle_code: str, driver_code: str) -> PlanningResources:
        vehicle = await self._vehicles.get_by_code(vehicle_code)
        if vehicle is None:
            raise VehicleNotFoundError(f"No existe el vehículo {vehicle_code}.")
        driver = await self._drivers.get_by_code(driver_code)
        if driver is None:
            raise DriverNotFoundError(f"No existe el conductor {driver_code}.")
        vehicle.ensure_available_for_trip()
        driver.ensure_available_for_trip()
        await self._require_gateway(vehicle.id, vehicle.code)
        return PlanningResources(vehicle_id=vehicle.id, driver_id=driver.id)

    async def allocate(
        self, *, trip_id: uuid.UUID, vehicle_id: uuid.UUID, driver_id: uuid.UUID, now: datetime
    ) -> uuid.UUID:
        vehicle = await self._vehicles.get_by_id(vehicle_id)
        driver = await self._drivers.get_by_id(driver_id)
        if vehicle is None:
            raise VehicleNotFoundError("El vehículo del viaje ya no existe.")
        if driver is None:
            raise DriverNotFoundError("El conductor del viaje ya no existe.")
        gateway_id = await self._require_gateway(vehicle.id, vehicle.code)
        vehicle.depart_on_trip()
        driver.assign_to_trip()
        await self._vehicles.save(vehicle)
        await self._drivers.save(driver)
        await self._driver_assignments.add(
            VehicleDriverAssignment.open(vehicle_id=vehicle.id, driver_id=driver.id, trip_id=trip_id, now=now)
        )
        return gateway_id

    async def release(self, *, trip_id: uuid.UUID, vehicle_id: uuid.UUID, driver_id: uuid.UUID, now: datetime) -> None:
        vehicle = await self._vehicles.get_by_id(vehicle_id)
        if vehicle is not None:
            vehicle.return_from_trip()
            await self._vehicles.save(vehicle)
        driver = await self._drivers.get_by_id(driver_id)
        if driver is not None:
            driver.release_from_trip()
            await self._drivers.save(driver)
        assignment = await self._driver_assignments.get_open_for_trip(trip_id)
        if assignment is not None:
            assignment.release(now)
            await self._driver_assignments.save(assignment)

    async def _require_gateway(self, vehicle_id: uuid.UUID, vehicle_code: str) -> uuid.UUID:
        gateway = await self._devices.find_active_gateway_for_vehicle(vehicle_id)
        if gateway is None:
            raise VehicleWithoutDeviceError(
                f"El vehículo {vehicle_code} no tiene un Edge Gateway activo asignado; no puede generar telemetría."
            )
        return gateway.id
