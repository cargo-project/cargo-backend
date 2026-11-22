from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.modules.fleet.domain.exceptions.fleet_errors import DeviceNotAssignableError
from app.modules.fleet.domain.services.connection_status_policy import (
    ConnectionStatus,
    derive_connection_status,
)
from app.modules.fleet.domain.services.field_rules import normalise_code, require_text
from app.shared.domain.entity import Entity


class IoTDeviceType(StrEnum):
    EDGE_GATEWAY = "edge_gateway"  # Raspberry Pi: es la que publica la telemetría
    GNSS = "gnss"  # módulo GNSS (solo inventario)


@dataclass(eq=False)
class IoTDevice(Entity):
    """Raíz de agregado de un dispositivo a bordo.

    online/offline no se guarda: sale de la hora de la última conexión, así nunca
    contradice la realidad. Lo único que decide el usuario es is_active.
    """

    id: uuid.UUID
    code: str
    device_type: IoTDeviceType
    serial_number: str
    firmware_version: str
    is_active: bool
    created_at: datetime
    vehicle_id: uuid.UUID | None = None
    last_connection_at: datetime | None = None

    @classmethod
    def register(
        cls,
        *,
        code: str,
        device_type: IoTDeviceType,
        serial_number: str,
        firmware_version: str,
        is_active: bool,
        now: datetime,
    ) -> IoTDevice:
        return cls(
            id=uuid.uuid4(),
            code=normalise_code(code, label="dispositivo"),
            device_type=device_type,
            serial_number=require_text(serial_number, label="serie", min_length=3, max_length=60),
            firmware_version=require_text(firmware_version, label="firmware", max_length=30),
            is_active=is_active,
            created_at=now,
        )

    @property
    def publishes_telemetry(self) -> bool:
        return self.device_type == IoTDeviceType.EDGE_GATEWAY

    def update_details(self, *, device_type: IoTDeviceType, serial_number: str, firmware_version: str) -> None:
        self.device_type = device_type
        self.serial_number = require_text(serial_number, label="serie", min_length=3, max_length=60)
        self.firmware_version = require_text(firmware_version, label="firmware", max_length=30)

    def activate(self) -> None:
        self.is_active = True

    def deactivate(self) -> None:
        self.is_active = False

    def assign_to(self, vehicle_id: uuid.UUID) -> None:
        if not self.is_active:
            raise DeviceNotAssignableError(f"El dispositivo {self.code} está inactivo.")
        self.vehicle_id = vehicle_id

    def unassign(self) -> None:
        self.vehicle_id = None

    def record_connection(self, at: datetime) -> None:
        if self.last_connection_at is None or at > self.last_connection_at:
            self.last_connection_at = at

    def connection_status(self, now: datetime, online_window: timedelta) -> ConnectionStatus:
        return derive_connection_status(
            is_active=self.is_active,
            last_connection_at=self.last_connection_at,
            now=now,
            online_window=online_window,
        )
