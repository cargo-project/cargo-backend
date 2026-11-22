from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class VehicleData:
    code: str
    plate: str
    brand: str
    model: str
    description: str
    status: str


@dataclass(frozen=True, slots=True)
class DriverData:
    first_name: str
    last_name: str
    document_number: str
    license_number: str
    phone: str
    status: str
    code: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceData:
    code: str
    device_type: str
    serial_number: str
    firmware_version: str
    is_active: bool
    vehicle_code: str | None


@dataclass(frozen=True, slots=True)
class VehicleView:
    id: uuid.UUID
    code: str
    plate: str
    brand: str
    model: str
    description: str
    status: str
    current_driver_name: str | None
    current_trip_code: str | None
    last_signal_at: datetime | None


@dataclass(frozen=True, slots=True)
class DriverView:
    id: uuid.UUID
    code: str
    first_name: str
    last_name: str
    document_number: str
    license_number: str
    phone: str
    status: str
    vehicle_code: str | None
    current_trip_code: str | None


@dataclass(frozen=True, slots=True)
class DeviceView:
    id: uuid.UUID
    code: str
    device_type: str
    serial_number: str
    firmware_version: str
    vehicle_code: str | None
    is_active: bool
    connection_status: str
    last_connection_at: datetime | None
