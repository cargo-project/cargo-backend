from __future__ import annotations

import uuid

from app.modules.fleet.application.dto.fleet_dto import VehicleData, VehicleView
from app.modules.fleet.application.ports.fleet_read_model import FleetReadModel
from app.modules.fleet.domain.entities.vehicle import Vehicle, VehicleStatus
from app.modules.fleet.domain.exceptions.fleet_errors import (
    DuplicateFleetResourceError,
    InvalidFleetDataError,
    VehicleNotFoundError,
)
from app.modules.fleet.domain.repositories.fleet_repositories import VehicleRepository
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


def _parse_status(raw: str) -> VehicleStatus:
    try:
        return VehicleStatus(raw)
    except ValueError as error:
        raise InvalidFleetDataError(f"Estado de vehículo desconocido: {raw}") from error


async def _view_or_fail(read_model: FleetReadModel, code: str) -> VehicleView:
    view = await read_model.get_vehicle(code)
    if view is None:
        raise VehicleNotFoundError(f"No existe el vehículo {code}.")
    return view


class ListVehiclesUseCase:
    def __init__(self, read_model: FleetReadModel) -> None:
        self._read_model = read_model

    async def execute(self) -> list[VehicleView]:
        return await self._read_model.list_vehicles()


class GetVehicleUseCase:
    def __init__(self, read_model: FleetReadModel) -> None:
        self._read_model = read_model

    async def execute(self, code: str) -> VehicleView:
        return await _view_or_fail(self._read_model, code.upper())


class CreateVehicleUseCase:
    def __init__(
        self,
        vehicles: VehicleRepository,
        read_model: FleetReadModel,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        self._vehicles = vehicles
        self._read_model = read_model
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, data: VehicleData, *, actor_id: uuid.UUID) -> VehicleView:
        vehicle = Vehicle.register(
            code=data.code,
            plate=data.plate,
            brand=data.brand,
            model=data.model,
            description=data.description,
            status=_parse_status(data.status),
            now=self._clock.now(),
        )
        if await self._vehicles.get_by_code(vehicle.code) is not None:
            raise DuplicateFleetResourceError(f"Ya existe un vehículo con código {vehicle.code}.")
        if await self._vehicles.exists_with_plate(vehicle.plate):
            raise DuplicateFleetResourceError(f"Ya existe un vehículo con placa {vehicle.plate}.")
        await self._vehicles.add(vehicle)
        await self._audit.record(
            action="vehicle.created", entity_type="vehicle", entity_id=vehicle.code, actor_id=actor_id
        )
        await self._uow.commit()
        return await _view_or_fail(self._read_model, vehicle.code)


class UpdateVehicleUseCase:
    def __init__(
        self, vehicles: VehicleRepository, read_model: FleetReadModel, uow: UnitOfWork, audit: AuditLog
    ) -> None:
        self._vehicles = vehicles
        self._read_model = read_model
        self._uow = uow
        self._audit = audit

    async def execute(self, code: str, data: VehicleData, *, actor_id: uuid.UUID) -> VehicleView:
        vehicle = await self._vehicles.get_by_code(code.upper())
        if vehicle is None:
            raise VehicleNotFoundError(f"No existe el vehículo {code}.")
        vehicle.update_details(plate=data.plate, brand=data.brand, model=data.model, description=data.description)
        if await self._vehicles.exists_with_plate(vehicle.plate, excluding=vehicle.id):
            raise DuplicateFleetResourceError(f"Ya existe un vehículo con placa {vehicle.plate}.")
        vehicle.change_status(_parse_status(data.status))
        await self._vehicles.save(vehicle)
        await self._audit.record(
            action="vehicle.updated", entity_type="vehicle", entity_id=vehicle.code, actor_id=actor_id
        )
        await self._uow.commit()
        return await _view_or_fail(self._read_model, vehicle.code)
