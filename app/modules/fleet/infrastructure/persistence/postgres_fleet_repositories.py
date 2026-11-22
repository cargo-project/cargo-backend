"""Repositorios PostgreSQL de flota (acá vive el mapeo ORM <-> dominio)."""

from __future__ import annotations

import uuid

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fleet.domain.entities.assignments import (
    VehicleDeviceAssignment,
    VehicleDriverAssignment,
)
from app.modules.fleet.domain.entities.driver import Driver, DriverStatus
from app.modules.fleet.domain.entities.iot_device import IoTDevice, IoTDeviceType
from app.modules.fleet.domain.entities.vehicle import Vehicle, VehicleStatus
from app.modules.fleet.infrastructure.persistence.assignment_models import (
    VehicleDeviceAssignmentModel,
    VehicleDriverAssignmentModel,
)
from app.modules.fleet.infrastructure.persistence.driver_model import DriverModel
from app.modules.fleet.infrastructure.persistence.iot_device_model import IoTDeviceModel
from app.modules.fleet.infrastructure.persistence.vehicle_model import VehicleModel


class PostgresVehicleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(m: VehicleModel) -> Vehicle:
        return Vehicle(
            id=m.id,
            code=m.code,
            plate=m.plate,
            brand=m.brand,
            model=m.model,
            description=m.description,
            status=VehicleStatus(m.status),
            created_at=m.created_at,
        )

    @staticmethod
    def _copy(v: Vehicle, m: VehicleModel) -> VehicleModel:
        m.id, m.code, m.plate, m.brand, m.model = v.id, v.code, v.plate, v.brand, v.model
        m.description, m.status, m.created_at = v.description, v.status.value, v.created_at
        return m

    async def get_by_id(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        model = await self._session.get(VehicleModel, vehicle_id)
        return self._to_domain(model) if model else None

    async def get_by_code(self, code: str) -> Vehicle | None:
        model = await self._session.scalar(select(VehicleModel).where(VehicleModel.code == code))
        return self._to_domain(model) if model else None

    async def exists_with_plate(self, plate: str, *, excluding: uuid.UUID | None = None) -> bool:
        condition = VehicleModel.plate == plate
        if excluding is not None:
            condition = condition & (VehicleModel.id != excluding)
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def add(self, vehicle: Vehicle) -> None:
        self._session.add(self._copy(vehicle, VehicleModel()))
        await self._session.flush()

    async def save(self, vehicle: Vehicle) -> None:
        model = await self._session.get(VehicleModel, vehicle.id)
        if model is None:
            await self.add(vehicle)
            return
        self._copy(vehicle, model)
        await self._session.flush()


class PostgresDriverRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(m: DriverModel) -> Driver:
        return Driver(
            id=m.id,
            code=m.code,
            first_name=m.first_name,
            last_name=m.last_name,
            document_number=m.document_number,
            license_number=m.license_number,
            phone=m.phone,
            status=DriverStatus(m.status),
            created_at=m.created_at,
        )

    @staticmethod
    def _copy(d: Driver, m: DriverModel) -> DriverModel:
        m.id, m.code, m.first_name, m.last_name = d.id, d.code, d.first_name, d.last_name
        m.document_number, m.license_number, m.phone = d.document_number, d.license_number, d.phone
        m.status, m.created_at = d.status.value, d.created_at
        return m

    async def get_by_id(self, driver_id: uuid.UUID) -> Driver | None:
        model = await self._session.get(DriverModel, driver_id)
        return self._to_domain(model) if model else None

    async def get_by_code(self, code: str) -> Driver | None:
        model = await self._session.scalar(select(DriverModel).where(DriverModel.code == code))
        return self._to_domain(model) if model else None

    async def exists_with_document(self, document: str, *, excluding: uuid.UUID | None = None) -> bool:
        condition = DriverModel.document_number == document
        if excluding is not None:
            condition = condition & (DriverModel.id != excluding)
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def add(self, driver: Driver) -> None:
        self._session.add(self._copy(driver, DriverModel()))
        await self._session.flush()

    async def save(self, driver: Driver) -> None:
        model = await self._session.get(DriverModel, driver.id)
        if model is None:
            await self.add(driver)
            return
        self._copy(driver, model)
        await self._session.flush()


class PostgresIoTDeviceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(m: IoTDeviceModel) -> IoTDevice:
        return IoTDevice(
            id=m.id,
            code=m.code,
            device_type=IoTDeviceType(m.device_type),
            serial_number=m.serial_number,
            firmware_version=m.firmware_version,
            is_active=m.is_active,
            created_at=m.created_at,
            vehicle_id=m.vehicle_id,
            last_connection_at=m.last_connection_at,
        )

    @staticmethod
    def _copy(d: IoTDevice, m: IoTDeviceModel) -> IoTDeviceModel:
        m.id, m.code, m.device_type = d.id, d.code, d.device_type.value
        m.serial_number, m.firmware_version, m.is_active = d.serial_number, d.firmware_version, d.is_active
        m.vehicle_id, m.last_connection_at, m.created_at = d.vehicle_id, d.last_connection_at, d.created_at
        return m

    async def get_by_id(self, device_id: uuid.UUID) -> IoTDevice | None:
        model = await self._session.get(IoTDeviceModel, device_id)
        return self._to_domain(model) if model else None

    async def get_by_code(self, code: str) -> IoTDevice | None:
        model = await self._session.scalar(select(IoTDeviceModel).where(IoTDeviceModel.code == code))
        return self._to_domain(model) if model else None

    async def find_active_gateway_for_vehicle(self, vehicle_id: uuid.UUID) -> IoTDevice | None:
        model = await self._session.scalar(
            select(IoTDeviceModel).where(
                IoTDeviceModel.vehicle_id == vehicle_id,
                IoTDeviceModel.is_active.is_(True),
                IoTDeviceModel.device_type == IoTDeviceType.EDGE_GATEWAY.value,
            )
        )
        return self._to_domain(model) if model else None

    async def add(self, device: IoTDevice) -> None:
        self._session.add(self._copy(device, IoTDeviceModel()))
        await self._session.flush()

    async def save(self, device: IoTDevice) -> None:
        model = await self._session.get(IoTDeviceModel, device.id)
        if model is None:
            await self.add(device)
            return
        self._copy(device, model)
        await self._session.flush()


class PostgresDeviceAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_open_for_device(self, device_id: uuid.UUID) -> VehicleDeviceAssignment | None:
        m = await self._session.scalar(
            select(VehicleDeviceAssignmentModel).where(
                VehicleDeviceAssignmentModel.device_id == device_id,
                VehicleDeviceAssignmentModel.released_at.is_(None),
            )
        )
        if m is None:
            return None
        return VehicleDeviceAssignment(
            id=m.id,
            vehicle_id=m.vehicle_id,
            device_id=m.device_id,
            assigned_at=m.assigned_at,
            released_at=m.released_at,
        )

    async def add(self, assignment: VehicleDeviceAssignment) -> None:
        self._session.add(
            VehicleDeviceAssignmentModel(
                id=assignment.id,
                vehicle_id=assignment.vehicle_id,
                device_id=assignment.device_id,
                assigned_at=assignment.assigned_at,
                released_at=assignment.released_at,
            )
        )
        await self._session.flush()

    async def save(self, assignment: VehicleDeviceAssignment) -> None:
        model = await self._session.get(VehicleDeviceAssignmentModel, assignment.id)
        if model is not None:
            model.released_at = assignment.released_at
            await self._session.flush()


class PostgresDriverAssignmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_open_for_trip(self, trip_id: uuid.UUID) -> VehicleDriverAssignment | None:
        m = await self._session.scalar(
            select(VehicleDriverAssignmentModel).where(
                VehicleDriverAssignmentModel.trip_id == trip_id,
                VehicleDriverAssignmentModel.released_at.is_(None),
            )
        )
        if m is None:
            return None
        return VehicleDriverAssignment(
            id=m.id,
            vehicle_id=m.vehicle_id,
            driver_id=m.driver_id,
            trip_id=m.trip_id,
            assigned_at=m.assigned_at,
            released_at=m.released_at,
        )

    async def add(self, assignment: VehicleDriverAssignment) -> None:
        self._session.add(
            VehicleDriverAssignmentModel(
                id=assignment.id,
                vehicle_id=assignment.vehicle_id,
                driver_id=assignment.driver_id,
                trip_id=assignment.trip_id,
                assigned_at=assignment.assigned_at,
                released_at=assignment.released_at,
            )
        )
        await self._session.flush()

    async def save(self, assignment: VehicleDriverAssignment) -> None:
        model = await self._session.get(VehicleDriverAssignmentModel, assignment.id)
        if model is not None:
            model.released_at = assignment.released_at
            await self._session.flush()
