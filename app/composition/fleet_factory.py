from __future__ import annotations

from datetime import timedelta

from app.composition.scope import Scope
from app.modules.fleet.application.use_cases.device_use_cases import (
    AssignDeviceUseCase,
    DeviceAssignmentService,
    DeviceCommandUseCase,
    DeviceViewAssembler,
    ListIoTDevicesUseCase,
    RegisterIoTDeviceUseCase,
    UpdateIoTDeviceUseCase,
)
from app.modules.fleet.application.use_cases.driver_use_cases import (
    CreateDriverUseCase,
    ListDriversUseCase,
    UpdateDriverUseCase,
)
from app.modules.fleet.application.use_cases.fleet_removal_use_cases import (
    DeleteDeviceUseCase,
    DeleteDriverUseCase,
    DeleteVehicleUseCase,
)
from app.modules.fleet.application.use_cases.vehicle_use_cases import (
    CreateVehicleUseCase,
    GetVehicleUseCase,
    ListVehiclesUseCase,
    UpdateVehicleUseCase,
)
from app.modules.fleet.infrastructure.persistence.postgres_fleet_removal_repository import (
    PostgresFleetRemovalRepository,
)
from app.modules.fleet.infrastructure.persistence.postgres_fleet_repositories import (
    PostgresDeviceAssignmentRepository,
    PostgresDriverRepository,
    PostgresIoTDeviceRepository,
    PostgresVehicleRepository,
)
from app.modules.fleet.infrastructure.persistence.sql_fleet_read_model import SqlFleetReadModel


def _read_model(scope: Scope) -> SqlFleetReadModel:
    return SqlFleetReadModel(scope.session)


def list_vehicles(scope: Scope) -> ListVehiclesUseCase:
    return ListVehiclesUseCase(_read_model(scope))


def get_vehicle(scope: Scope) -> GetVehicleUseCase:
    return GetVehicleUseCase(_read_model(scope))


def create_vehicle(scope: Scope) -> CreateVehicleUseCase:
    return CreateVehicleUseCase(
        PostgresVehicleRepository(scope.session),
        _read_model(scope),
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def update_vehicle(scope: Scope) -> UpdateVehicleUseCase:
    return UpdateVehicleUseCase(PostgresVehicleRepository(scope.session), _read_model(scope), scope.uow, scope.audit)


def list_drivers(scope: Scope) -> ListDriversUseCase:
    return ListDriversUseCase(_read_model(scope))


def create_driver(scope: Scope) -> CreateDriverUseCase:
    return CreateDriverUseCase(
        PostgresDriverRepository(scope.session),
        _read_model(scope),
        scope.uow,
        scope.resources.clock,
        scope.audit,
    )


def update_driver(scope: Scope) -> UpdateDriverUseCase:
    return UpdateDriverUseCase(PostgresDriverRepository(scope.session), _read_model(scope), scope.uow, scope.audit)


def device_assembler(scope: Scope) -> DeviceViewAssembler:
    window = timedelta(seconds=scope.resources.settings.device_online_window_seconds)
    return DeviceViewAssembler(scope.resources.clock, window)


def list_devices(scope: Scope) -> ListIoTDevicesUseCase:
    return ListIoTDevicesUseCase(_read_model(scope), device_assembler(scope))


def _device_command[T: DeviceCommandUseCase](use_case: type[T], scope: Scope) -> T:
    devices = PostgresIoTDeviceRepository(scope.session)
    assignment_service = DeviceAssignmentService(
        devices,
        PostgresVehicleRepository(scope.session),
        PostgresDeviceAssignmentRepository(scope.session),
        scope.resources.clock,
    )
    return use_case(
        devices=devices,
        assignment_service=assignment_service,
        read_model=_read_model(scope),
        assembler=device_assembler(scope),
        uow=scope.uow,
        clock=scope.resources.clock,
        audit=scope.audit,
    )


def register_device(scope: Scope) -> RegisterIoTDeviceUseCase:
    return _device_command(RegisterIoTDeviceUseCase, scope)


def update_device(scope: Scope) -> UpdateIoTDeviceUseCase:
    return _device_command(UpdateIoTDeviceUseCase, scope)


def assign_device(scope: Scope) -> AssignDeviceUseCase:
    return _device_command(AssignDeviceUseCase, scope)


def delete_vehicle(scope: Scope) -> DeleteVehicleUseCase:
    return DeleteVehicleUseCase(
        PostgresVehicleRepository(scope.session), PostgresFleetRemovalRepository(scope.session), scope.uow, scope.audit
    )


def delete_driver(scope: Scope) -> DeleteDriverUseCase:
    return DeleteDriverUseCase(
        PostgresDriverRepository(scope.session), PostgresFleetRemovalRepository(scope.session), scope.uow, scope.audit
    )


def delete_device(scope: Scope) -> DeleteDeviceUseCase:
    return DeleteDeviceUseCase(
        PostgresIoTDeviceRepository(scope.session),
        PostgresFleetRemovalRepository(scope.session),
        scope.uow,
        scope.audit,
    )
