from __future__ import annotations

import uuid
from datetime import timedelta

from app.modules.fleet.application.dto.fleet_dto import DeviceData, DeviceView
from app.modules.fleet.application.ports.fleet_read_model import DeviceRow, FleetReadModel
from app.modules.fleet.domain.entities.assignments import VehicleDeviceAssignment
from app.modules.fleet.domain.entities.iot_device import IoTDevice, IoTDeviceType
from app.modules.fleet.domain.entities.vehicle import VehicleStatus
from app.modules.fleet.domain.exceptions.fleet_errors import (
    DeviceNotAssignableError,
    DuplicateFleetResourceError,
    InvalidFleetDataError,
    IoTDeviceNotFoundError,
    VehicleNotFoundError,
)
from app.modules.fleet.domain.repositories.fleet_repositories import (
    DeviceAssignmentRepository,
    IoTDeviceRepository,
    VehicleRepository,
)
from app.modules.fleet.domain.services.connection_status_policy import derive_connection_status
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


def _parse_type(raw: str) -> IoTDeviceType:
    try:
        return IoTDeviceType(raw)
    except ValueError as error:
        raise InvalidFleetDataError(f"Tipo de dispositivo desconocido: {raw}") from error


class DeviceViewAssembler:
    """Convierte las filas leídas en vistas aplicando la regla de estado de conexión."""

    def __init__(self, clock: Clock, online_window: timedelta) -> None:
        self._clock = clock
        self._online_window = online_window

    def assemble(self, row: DeviceRow) -> DeviceView:
        status = derive_connection_status(
            is_active=row.is_active,
            last_connection_at=row.last_connection_at,
            now=self._clock.now(),
            online_window=self._online_window,
        )
        return DeviceView(
            id=row.id,
            code=row.code,
            device_type=row.device_type,
            serial_number=row.serial_number,
            firmware_version=row.firmware_version,
            vehicle_code=row.vehicle_code,
            is_active=row.is_active,
            connection_status=status.value,
            last_connection_at=row.last_connection_at,
        )


class DeviceAssignmentService:
    """Servicio de aplicación con las reglas de emparejamiento que usan varios casos de uso.

    Reglas: el dispositivo tiene que estar activo para asignarse; un vehículo en viaje no
    puede cambiar de dispositivo; un vehículo tiene como máximo un gateway de telemetría.
    Cada cambio queda como VehicleDeviceAssignment para tener historial.
    """

    def __init__(
        self,
        devices: IoTDeviceRepository,
        vehicles: VehicleRepository,
        assignments: DeviceAssignmentRepository,
        clock: Clock,
    ) -> None:
        self._devices = devices
        self._vehicles = vehicles
        self._assignments = assignments
        self._clock = clock

    async def assign(self, device: IoTDevice, vehicle_code: str) -> None:
        vehicle = await self._vehicles.get_by_code(vehicle_code.upper())
        if vehicle is None:
            raise VehicleNotFoundError(f"No existe el vehículo {vehicle_code}.")
        if device.vehicle_id == vehicle.id:
            return
        if vehicle.status == VehicleStatus.ON_ROUTE:
            raise DeviceNotAssignableError(
                f"El vehículo {vehicle.code} está en ruta; no se puede cambiar su dispositivo."
            )
        if device.publishes_telemetry:
            current = await self._devices.find_active_gateway_for_vehicle(vehicle.id)
            if current is not None and current.id != device.id:
                raise DeviceNotAssignableError(
                    f"El vehículo {vehicle.code} ya tiene el gateway {current.code} asignado."
                )
        await self.unassign(device)
        device.assign_to(vehicle.id)
        await self._assignments.add(
            VehicleDeviceAssignment.open(vehicle_id=vehicle.id, device_id=device.id, now=self._clock.now())
        )

    async def unassign(self, device: IoTDevice) -> None:
        if device.vehicle_id is None:
            return
        vehicle = await self._vehicles.get_by_id(device.vehicle_id)
        if vehicle is not None and vehicle.status == VehicleStatus.ON_ROUTE:
            raise DeviceNotAssignableError(
                f"El vehículo {vehicle.code} está en ruta; no se puede retirar su dispositivo."
            )
        open_assignment = await self._assignments.get_open_for_device(device.id)
        if open_assignment is not None:
            open_assignment.release(self._clock.now())
            await self._assignments.save(open_assignment)
        device.unassign()


class ListIoTDevicesUseCase:
    def __init__(self, read_model: FleetReadModel, assembler: DeviceViewAssembler) -> None:
        self._read_model = read_model
        self._assembler = assembler

    async def execute(self) -> list[DeviceView]:
        return [self._assembler.assemble(row) for row in await self._read_model.list_devices()]


class DeviceCommandUseCase:
    """Dependencias comunes de los casos de uso que modifican dispositivos."""

    def __init__(
        self,
        devices: IoTDeviceRepository,
        assignment_service: DeviceAssignmentService,
        read_model: FleetReadModel,
        assembler: DeviceViewAssembler,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        self._devices = devices
        self._assignment_service = assignment_service
        self._read_model = read_model
        self._assembler = assembler
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def _apply_assignment(self, device: IoTDevice, vehicle_code: str | None) -> None:
        if vehicle_code:
            await self._assignment_service.assign(device, vehicle_code)
        else:
            await self._assignment_service.unassign(device)

    async def _view(self, code: str) -> DeviceView:
        row = await self._read_model.get_device(code)
        if row is None:
            raise IoTDeviceNotFoundError(f"No existe el dispositivo {code}.")
        return self._assembler.assemble(row)


class RegisterIoTDeviceUseCase(DeviceCommandUseCase):
    async def execute(self, data: DeviceData, *, actor_id: uuid.UUID) -> DeviceView:
        device = IoTDevice.register(
            code=data.code,
            device_type=_parse_type(data.device_type),
            serial_number=data.serial_number,
            firmware_version=data.firmware_version,
            is_active=data.is_active,
            now=self._clock.now(),
        )
        if await self._devices.get_by_code(device.code) is not None:
            raise DuplicateFleetResourceError(f"Ya existe un dispositivo con código {device.code}.")
        await self._devices.add(device)
        await self._apply_assignment(device, data.vehicle_code)
        await self._devices.save(device)
        await self._audit.record(
            action="device.registered", entity_type="device", entity_id=device.code, actor_id=actor_id
        )
        await self._uow.commit()
        return await self._view(device.code)


class UpdateIoTDeviceUseCase(DeviceCommandUseCase):
    async def execute(self, code: str, data: DeviceData, *, actor_id: uuid.UUID) -> DeviceView:
        device = await self._devices.get_by_code(code.upper())
        if device is None:
            raise IoTDeviceNotFoundError(f"No existe el dispositivo {code}.")
        device.update_details(
            device_type=_parse_type(data.device_type),
            serial_number=data.serial_number,
            firmware_version=data.firmware_version,
        )
        if data.is_active:
            device.activate()
            await self._apply_assignment(device, data.vehicle_code)
        else:
            await self._assignment_service.unassign(device)
            device.deactivate()
        await self._devices.save(device)
        await self._audit.record(
            action="device.updated",
            entity_type="device",
            entity_id=device.code,
            actor_id=actor_id,
            details={"vehicle": data.vehicle_code, "active": data.is_active},
        )
        await self._uow.commit()
        return await self._view(device.code)


class AssignDeviceUseCase(DeviceCommandUseCase):
    """Endpoint explícito de emparejamiento (PUT /devices/{code}/assignment)."""

    async def execute(self, code: str, vehicle_code: str | None, *, actor_id: uuid.UUID) -> DeviceView:
        device = await self._devices.get_by_code(code.upper())
        if device is None:
            raise IoTDeviceNotFoundError(f"No existe el dispositivo {code}.")
        await self._apply_assignment(device, vehicle_code)
        await self._devices.save(device)
        await self._audit.record(
            action="device.assignment_changed",
            entity_type="device",
            entity_id=device.code,
            actor_id=actor_id,
            details={"vehicle": vehicle_code},
        )
        await self._uow.commit()
        return await self._view(device.code)
