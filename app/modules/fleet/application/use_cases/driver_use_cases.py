from __future__ import annotations

import secrets
import uuid

from app.modules.fleet.application.dto.fleet_dto import DriverData, DriverView
from app.modules.fleet.application.ports.fleet_read_model import FleetReadModel
from app.modules.fleet.domain.entities.driver import Driver, DriverStatus
from app.modules.fleet.domain.exceptions.fleet_errors import (
    DriverNotFoundError,
    DuplicateFleetResourceError,
    InvalidFleetDataError,
)
from app.modules.fleet.domain.repositories.fleet_repositories import DriverRepository
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


def _parse_status(raw: str) -> DriverStatus:
    try:
        return DriverStatus(raw)
    except ValueError as error:
        raise InvalidFleetDataError(f"Estado de conductor desconocido: {raw}") from error


async def _view_or_fail(read_model: FleetReadModel, code: str) -> DriverView:
    view = await read_model.get_driver(code)
    if view is None:
        raise DriverNotFoundError(f"No existe el conductor {code}.")
    return view


class ListDriversUseCase:
    def __init__(self, read_model: FleetReadModel) -> None:
        self._read_model = read_model

    async def execute(self) -> list[DriverView]:
        return await self._read_model.list_drivers()


class CreateDriverUseCase:
    """Registra un conductor. El frontend no manda código, así que se genera uno (DRV-XXXXXX)."""

    def __init__(
        self,
        drivers: DriverRepository,
        read_model: FleetReadModel,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        self._drivers = drivers
        self._read_model = read_model
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, data: DriverData, *, actor_id: uuid.UUID) -> DriverView:
        code = data.code or await self._unique_code()
        driver = Driver.register(
            code=code,
            first_name=data.first_name,
            last_name=data.last_name,
            document_number=data.document_number,
            license_number=data.license_number,
            phone=data.phone,
            status=_parse_status(data.status),
            now=self._clock.now(),
        )
        if await self._drivers.get_by_code(driver.code) is not None:
            raise DuplicateFleetResourceError(f"Ya existe un conductor con código {driver.code}.")
        if await self._drivers.exists_with_document(driver.document_number):
            raise DuplicateFleetResourceError("Ya existe un conductor con ese documento.")
        await self._drivers.add(driver)
        await self._audit.record(
            action="driver.created", entity_type="driver", entity_id=driver.code, actor_id=actor_id
        )
        await self._uow.commit()
        return await _view_or_fail(self._read_model, driver.code)

    async def _unique_code(self) -> str:
        while True:
            candidate = f"DRV-{secrets.token_hex(3).upper()}"
            if await self._drivers.get_by_code(candidate) is None:
                return candidate


class UpdateDriverUseCase:
    def __init__(self, drivers: DriverRepository, read_model: FleetReadModel, uow: UnitOfWork, audit: AuditLog) -> None:
        self._drivers = drivers
        self._read_model = read_model
        self._uow = uow
        self._audit = audit

    async def execute(self, code: str, data: DriverData, *, actor_id: uuid.UUID) -> DriverView:
        driver = await self._drivers.get_by_code(code.upper())
        if driver is None:
            raise DriverNotFoundError(f"No existe el conductor {code}.")
        driver.update_details(
            first_name=data.first_name,
            last_name=data.last_name,
            document_number=data.document_number,
            license_number=data.license_number,
            phone=data.phone,
        )
        if await self._drivers.exists_with_document(driver.document_number, excluding=driver.id):
            raise DuplicateFleetResourceError("Ya existe un conductor con ese documento.")
        driver.change_status(_parse_status(data.status))
        await self._drivers.save(driver)
        await self._audit.record(
            action="driver.updated", entity_type="driver", entity_id=driver.code, actor_id=actor_id
        )
        await self._uow.commit()
        return await _view_or_fail(self._read_model, driver.code)
