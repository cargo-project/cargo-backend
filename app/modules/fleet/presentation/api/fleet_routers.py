"""Adaptadores HTTP delgados: validan la entrada, llaman a un caso de uso y mapean el resultado."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.composition import fleet_factory
from app.core.http.dependencies import ScopeDep
from app.core.http.envelope import ERROR_RESPONSES, DataEnvelope, wrap
from app.modules.fleet.presentation.schemas.fleet_schemas import (
    DeviceAssignmentRequest,
    DeviceRequest,
    DeviceResponse,
    DriverRequest,
    DriverResponse,
    VehicleRequest,
    VehicleResponse,
)
from app.modules.identity.presentation.api.auth_dependencies import CurrentUser

vehicles_router = APIRouter(prefix="/vehicles", tags=["vehicles"], responses=ERROR_RESPONSES)
drivers_router = APIRouter(prefix="/drivers", tags=["drivers"], responses=ERROR_RESPONSES)
devices_router = APIRouter(prefix="/devices", tags=["devices"], responses=ERROR_RESPONSES)


@vehicles_router.get("", summary="List vehicles with current driver, trip and last signal")
async def list_vehicles(_: CurrentUser, scope: ScopeDep) -> DataEnvelope[list[VehicleResponse]]:
    views = await fleet_factory.list_vehicles(scope).execute()
    return wrap([VehicleResponse.from_view(view) for view in views])


@vehicles_router.get("/{code}", summary="Vehicle detail")
async def get_vehicle(code: str, _: CurrentUser, scope: ScopeDep) -> DataEnvelope[VehicleResponse]:
    return wrap(VehicleResponse.from_view(await fleet_factory.get_vehicle(scope).execute(code)))


@vehicles_router.post("", status_code=status.HTTP_201_CREATED, summary="Register a vehicle")
async def create_vehicle(body: VehicleRequest, user: CurrentUser, scope: ScopeDep) -> DataEnvelope[VehicleResponse]:
    view = await fleet_factory.create_vehicle(scope).execute(body.to_data(), actor_id=user.id)
    return wrap(VehicleResponse.from_view(view))


@vehicles_router.put("/{code}", summary="Update vehicle data and manual status")
async def update_vehicle(
    code: str, body: VehicleRequest, user: CurrentUser, scope: ScopeDep
) -> DataEnvelope[VehicleResponse]:
    view = await fleet_factory.update_vehicle(scope).execute(code, body.to_data(), actor_id=user.id)
    return wrap(VehicleResponse.from_view(view))


@drivers_router.get("", summary="List drivers")
async def list_drivers(_: CurrentUser, scope: ScopeDep) -> DataEnvelope[list[DriverResponse]]:
    views = await fleet_factory.list_drivers(scope).execute()
    return wrap([DriverResponse.from_view(view) for view in views])


@drivers_router.post("", status_code=status.HTTP_201_CREATED, summary="Register a driver")
async def create_driver(body: DriverRequest, user: CurrentUser, scope: ScopeDep) -> DataEnvelope[DriverResponse]:
    view = await fleet_factory.create_driver(scope).execute(body.to_data(), actor_id=user.id)
    return wrap(DriverResponse.from_view(view))


@drivers_router.put("/{code}", summary="Update a driver")
async def update_driver(
    code: str, body: DriverRequest, user: CurrentUser, scope: ScopeDep
) -> DataEnvelope[DriverResponse]:
    view = await fleet_factory.update_driver(scope).execute(code, body.to_data(), actor_id=user.id)
    return wrap(DriverResponse.from_view(view))


@devices_router.get("", summary="List IoT devices with derived connection status")
async def list_devices(_: CurrentUser, scope: ScopeDep) -> DataEnvelope[list[DeviceResponse]]:
    views = await fleet_factory.list_devices(scope).execute()
    return wrap([DeviceResponse.from_view(view) for view in views])


@devices_router.post("", status_code=status.HTTP_201_CREATED, summary="Register an IoT device")
async def register_device(body: DeviceRequest, user: CurrentUser, scope: ScopeDep) -> DataEnvelope[DeviceResponse]:
    view = await fleet_factory.register_device(scope).execute(body.to_data(), actor_id=user.id)
    return wrap(DeviceResponse.from_view(view))


@devices_router.put("/{code}", summary="Update a device (including its vehicle assignment)")
async def update_device(
    code: str, body: DeviceRequest, user: CurrentUser, scope: ScopeDep
) -> DataEnvelope[DeviceResponse]:
    view = await fleet_factory.update_device(scope).execute(code, body.to_data(), actor_id=user.id)
    return wrap(DeviceResponse.from_view(view))


@devices_router.put("/{code}/assignment", summary="Assign or release the device's vehicle")
async def assign_device(
    code: str, body: DeviceAssignmentRequest, user: CurrentUser, scope: ScopeDep
) -> DataEnvelope[DeviceResponse]:
    view = await fleet_factory.assign_device(scope).execute(code, body.vehicle_code, actor_id=user.id)
    return wrap(DeviceResponse.from_view(view))
