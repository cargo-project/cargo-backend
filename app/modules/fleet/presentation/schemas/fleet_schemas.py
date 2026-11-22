"""Contratos HTTP de las pantallas de flota (igual que ApiVehicle, ApiDriver y ApiDevice).

Los valores que el frontend escribe distinto al dominio (onRoute vs on_route,
Edge Gateway vs edge_gateway) se traducen acá, para que las convenciones del
frontend no se metan en el dominio.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.core.http.envelope import CamelModel
from app.modules.fleet.application.dto.fleet_dto import (
    DeviceData,
    DeviceView,
    DriverData,
    DriverView,
    VehicleData,
    VehicleView,
)

ApiVehicleStatus = Literal["available", "onRoute", "stopped", "maintenance", "offline"]
ApiDriverStatus = Literal["available", "assigned", "inactive"]
ApiDeviceType = Literal["Edge Gateway", "GNSS"]
ApiDeviceStatus = Literal["online", "offline", "inactive"]

_VEHICLE_STATUS_TO_DOMAIN = {"onRoute": "on_route"}
_VEHICLE_STATUS_TO_API = {"on_route": "onRoute"}
_DEVICE_TYPE_TO_DOMAIN = {"Edge Gateway": "edge_gateway", "GNSS": "gnss"}
_DEVICE_TYPE_TO_API = {value: key for key, value in _DEVICE_TYPE_TO_DOMAIN.items()}


class VehicleRequest(CamelModel):
    code: str = Field(pattern=r"^[A-Za-z0-9-]{2,24}$")
    plate: str = Field(min_length=3, max_length=16)
    brand: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=500)
    status: ApiVehicleStatus = "available"

    def to_data(self) -> VehicleData:
        return VehicleData(
            code=self.code,
            plate=self.plate,
            brand=self.brand,
            model=self.model,
            description=self.description,
            status=_VEHICLE_STATUS_TO_DOMAIN.get(self.status, self.status),
        )


class VehicleResponse(CamelModel):
    id: uuid.UUID
    code: str
    plate: str
    brand: str
    model: str
    description: str
    status: ApiVehicleStatus
    current_driver: str | None = None
    current_trip: str | None = None
    last_signal_at: datetime | None = None

    @classmethod
    def from_view(cls, view: VehicleView) -> VehicleResponse:
        return cls(
            id=view.id,
            code=view.code,
            plate=view.plate,
            brand=view.brand,
            model=view.model,
            description=view.description,
            status=_VEHICLE_STATUS_TO_API.get(view.status, view.status),
            current_driver=view.current_driver_name,
            current_trip=view.current_trip_code,
            last_signal_at=view.last_signal_at,
        )


class DriverRequest(CamelModel):
    code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{2,24}$")
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    document: str = Field(min_length=6, max_length=20)
    license: str = Field(min_length=3, max_length=20)
    phone: str = Field(min_length=6, max_length=20)
    status: ApiDriverStatus = "available"

    def to_data(self) -> DriverData:
        return DriverData(
            code=self.code,
            first_name=self.first_name,
            last_name=self.last_name,
            document_number=self.document,
            license_number=self.license,
            phone=self.phone,
            status=self.status,
        )


class DriverResponse(CamelModel):
    id: uuid.UUID
    code: str
    first_name: str
    last_name: str
    document: str
    license: str
    phone: str
    status: ApiDriverStatus
    vehicle: str | None = None
    current_trip: str | None = None

    @classmethod
    def from_view(cls, view: DriverView) -> DriverResponse:
        return cls(
            id=view.id,
            code=view.code,
            first_name=view.first_name,
            last_name=view.last_name,
            document=view.document_number,
            license=view.license_number,
            phone=view.phone,
            status=view.status,
            vehicle=view.vehicle_code,
            current_trip=view.current_trip_code,
        )


class DeviceRequest(CamelModel):
    code: str = Field(pattern=r"^[A-Za-z0-9-]{2,24}$")
    type: ApiDeviceType
    serial: str = Field(min_length=3, max_length=60)
    firmware: str = Field(min_length=1, max_length=30)
    vehicle_code: str | None = Field(default=None, max_length=24)
    status: ApiDeviceStatus = "offline"
    active: bool = True

    def to_data(self) -> DeviceData:
        # online/offline sale de la telemetría; solo "inactive" es decisión del usuario.
        return DeviceData(
            code=self.code,
            device_type=_DEVICE_TYPE_TO_DOMAIN[self.type],
            serial_number=self.serial,
            firmware_version=self.firmware,
            is_active=self.active and self.status != "inactive",
            vehicle_code=self.vehicle_code or None,
        )


class DeviceAssignmentRequest(CamelModel):
    vehicle_code: str | None = Field(default=None, max_length=24)


class DeviceResponse(CamelModel):
    id: uuid.UUID
    code: str
    type: ApiDeviceType
    serial: str
    firmware: str
    vehicle_code: str | None = None
    status: ApiDeviceStatus
    active: bool
    last_connection_at: datetime | None = None

    @classmethod
    def from_view(cls, view: DeviceView) -> DeviceResponse:
        return cls(
            id=view.id,
            code=view.code,
            type=_DEVICE_TYPE_TO_API[view.device_type],
            serial=view.serial_number,
            firmware=view.firmware_version,
            vehicle_code=view.vehicle_code,
            status=view.connection_status,
            active=view.is_active,
            last_connection_at=view.last_connection_at,
        )
