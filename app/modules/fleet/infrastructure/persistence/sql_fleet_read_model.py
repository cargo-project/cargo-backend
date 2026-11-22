"""Read model SQL para las pantallas de flota.

Usa SQL directo sobre las tablas en vez de importar los modelos ORM de otros módulos:
el lado de lectura puede cruzar contextos, el de escritura nunca.
"""

from __future__ import annotations

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fleet.application.dto.fleet_dto import DriverView, VehicleView
from app.modules.fleet.application.ports.fleet_read_model import DeviceRow

_VEHICLES_SQL = """
SELECT v.id, v.code, v.plate, v.brand, v.model, v.description, v.status,
       CASE WHEN d.id IS NULL THEN NULL ELSE d.first_name || ' ' || d.last_name END AS driver_name,
       t.code AS trip_code,
       (SELECT max(dev.last_connection_at) FROM iot_devices dev WHERE dev.vehicle_id = v.id) AS last_signal_at
FROM vehicles v
LEFT JOIN trips t ON t.vehicle_id = v.id AND t.status = 'ongoing'
LEFT JOIN drivers d ON d.id = t.driver_id
"""

_DRIVERS_SQL = """
SELECT d.id, d.code, d.first_name, d.last_name, d.document_number, d.license_number, d.phone, d.status,
       v.code AS vehicle_code, t.code AS trip_code
FROM drivers d
LEFT JOIN trips t ON t.driver_id = d.id AND t.status = 'ongoing'
LEFT JOIN vehicles v ON v.id = t.vehicle_id
"""

_DEVICES_SQL = """
SELECT dev.id, dev.code, dev.device_type, dev.serial_number, dev.firmware_version, dev.is_active,
       dev.last_connection_at, v.code AS vehicle_code
FROM iot_devices dev
LEFT JOIN vehicles v ON v.id = dev.vehicle_id
"""


def _vehicle(row: RowMapping) -> VehicleView:
    return VehicleView(
        id=row["id"],
        code=row["code"],
        plate=row["plate"],
        brand=row["brand"],
        model=row["model"],
        description=row["description"],
        status=row["status"],
        current_driver_name=row["driver_name"],
        current_trip_code=row["trip_code"],
        last_signal_at=row["last_signal_at"],
    )


def _driver(row: RowMapping) -> DriverView:
    return DriverView(
        id=row["id"],
        code=row["code"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        document_number=row["document_number"],
        license_number=row["license_number"],
        phone=row["phone"],
        status=row["status"],
        vehicle_code=row["vehicle_code"],
        current_trip_code=row["trip_code"],
    )


def _device(row: RowMapping) -> DeviceRow:
    return DeviceRow(
        id=row["id"],
        code=row["code"],
        device_type=row["device_type"],
        serial_number=row["serial_number"],
        firmware_version=row["firmware_version"],
        vehicle_code=row["vehicle_code"],
        is_active=row["is_active"],
        last_connection_at=row["last_connection_at"],
    )


class SqlFleetReadModel:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_vehicles(self) -> list[VehicleView]:
        rows = await self._session.execute(text(_VEHICLES_SQL + " ORDER BY v.code"))
        return [_vehicle(row) for row in rows.mappings()]

    async def get_vehicle(self, code: str) -> VehicleView | None:
        rows = await self._session.execute(text(_VEHICLES_SQL + " WHERE v.code = :code"), {"code": code})
        row = rows.mappings().first()
        return _vehicle(row) if row else None

    async def list_drivers(self) -> list[DriverView]:
        rows = await self._session.execute(text(_DRIVERS_SQL + " ORDER BY d.last_name, d.first_name"))
        return [_driver(row) for row in rows.mappings()]

    async def get_driver(self, code: str) -> DriverView | None:
        rows = await self._session.execute(text(_DRIVERS_SQL + " WHERE d.code = :code"), {"code": code})
        row = rows.mappings().first()
        return _driver(row) if row else None

    async def list_devices(self) -> list[DeviceRow]:
        rows = await self._session.execute(text(_DEVICES_SQL + " ORDER BY dev.code"))
        return [_device(row) for row in rows.mappings()]

    async def get_device(self, code: str) -> DeviceRow | None:
        rows = await self._session.execute(text(_DEVICES_SQL + " WHERE dev.code = :code"), {"code": code})
        row = rows.mappings().first()
        return _device(row) if row else None
