"""FleetRemovalRepository sobre PostgreSQL.

Los conteos miran tablas de otros módulos (viajes, telemetría) solo para decidir si el registro tiene
historial; por eso se consultan con SQL y no con sus modelos.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PostgresFleetRemovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _count(self, sql: str, entity_id: uuid.UUID) -> int:
        return int(await self._session.scalar(text(sql), {"id": entity_id}) or 0)

    async def _run(self, sql: str, entity_id: uuid.UUID) -> None:
        await self._session.execute(text(sql), {"id": entity_id})

    async def vehicle_trip_count(self, vehicle_id: uuid.UUID) -> int:
        return await self._count("SELECT count(*) FROM trips WHERE vehicle_id = :id", vehicle_id)

    async def driver_trip_count(self, driver_id: uuid.UUID) -> int:
        return await self._count("SELECT count(*) FROM trips WHERE driver_id = :id", driver_id)

    async def device_history_count(self, device_id: uuid.UUID) -> int:
        return await self._count(
            "SELECT (SELECT count(*) FROM trips WHERE device_id = :id)"
            " + (SELECT count(*) FROM telemetry_events WHERE device_id = :id)"
            # Un viaje configurado todavía no guarda el dispositivo: se mira el vehículo al que está asignado.
            " + (SELECT count(*) FROM trips t JOIN iot_devices d ON d.vehicle_id = t.vehicle_id"
            "    WHERE d.id = :id AND t.status IN ('configured', 'ongoing'))",
            device_id,
        )

    async def remove_vehicle(self, vehicle_id: uuid.UUID) -> None:
        # Sin viajes no hay asignaciones de conductor; las de dispositivo se borran y el dispositivo queda libre.
        await self._run("DELETE FROM vehicle_driver_assignments WHERE vehicle_id = :id", vehicle_id)
        await self._run("DELETE FROM vehicle_device_assignments WHERE vehicle_id = :id", vehicle_id)
        await self._run("UPDATE iot_devices SET vehicle_id = NULL WHERE vehicle_id = :id", vehicle_id)
        await self._run("DELETE FROM vehicles WHERE id = :id", vehicle_id)

    async def remove_driver(self, driver_id: uuid.UUID) -> None:
        await self._run("DELETE FROM vehicle_driver_assignments WHERE driver_id = :id", driver_id)
        await self._run("DELETE FROM drivers WHERE id = :id", driver_id)

    async def remove_device(self, device_id: uuid.UUID) -> None:
        await self._run("DELETE FROM vehicle_device_assignments WHERE device_id = :id", device_id)
        await self._run("DELETE FROM iot_devices WHERE id = :id", device_id)
