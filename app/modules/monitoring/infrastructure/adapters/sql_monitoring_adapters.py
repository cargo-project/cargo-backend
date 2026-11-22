"""Adaptadores SQL que le dan al monitoreo los datos de dispositivo y viaje que necesita."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.monitoring.application.dto.monitoring_dto import TripSummary
from app.modules.monitoring.domain.services.telemetry_acceptance_policy import TelemetryTripContext

_CONTEXT_SQL = text(
    """
    SELECT d.id AS device_id, d.code AS device_code, d.is_active AS device_active,
           t.id AS trip_id, t.code AS trip_code, t.status AS trip_status, t.device_id AS trip_device_id,
           t.started_at, COALESCE(t.completed_at, t.cancelled_at) AS ended_at, v.code AS vehicle_code
    FROM iot_devices d
    LEFT JOIN trips t ON t.id = :trip_id
    LEFT JOIN vehicles v ON v.id = t.vehicle_id
    WHERE d.code = :device_code
    """
)

_RECORD_CONNECTION_SQL = text(
    """
    UPDATE iot_devices SET last_connection_at = GREATEST(COALESCE(last_connection_at, :at), :at)
    WHERE id = :device_id
    """
)

_TRIP_SUMMARY_SQL = text(
    """
    SELECT t.id, t.code, t.status, v.code AS vehicle_code, d.first_name || ' ' || d.last_name AS driver_name
    FROM trips t JOIN vehicles v ON v.id = t.vehicle_id JOIN drivers d ON d.id = t.driver_id
    WHERE t.id = :trip_id
    """
)


class SqlTelemetryContextProvider:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, *, device_code: str, trip_id: uuid.UUID) -> TelemetryTripContext | None:
        row = (
            (await self._session.execute(_CONTEXT_SQL, {"device_code": device_code, "trip_id": trip_id}))
            .mappings()
            .first()
        )
        if row is None:
            return None
        return TelemetryTripContext(
            device_id=row["device_id"],
            device_code=row["device_code"],
            device_active=row["device_active"],
            trip_id=row["trip_id"],
            trip_code=row["trip_code"],
            vehicle_code=row["vehicle_code"],
            trip_status=row["trip_status"],
            trip_device_id=row["trip_device_id"],
            trip_started_at=row["started_at"],
            trip_ended_at=row["ended_at"],
        )


class SqlDeviceConnectionRecorder:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, device_id: uuid.UUID, at: datetime) -> None:
        await self._session.execute(_RECORD_CONNECTION_SQL, {"device_id": device_id, "at": at})


class SqlDeviceDirectory:
    """DeviceDirectory: búsqueda de solo lectura del código público de un dispositivo."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def code_of(self, device_id: uuid.UUID) -> str | None:
        code = await self._session.scalar(text("SELECT code FROM iot_devices WHERE id = :id"), {"id": device_id})
        return str(code) if code else None


class SqlMonitoringTripDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def describe(self, trip_id: uuid.UUID) -> TripSummary | None:
        row = (await self._session.execute(_TRIP_SUMMARY_SQL, {"trip_id": trip_id})).mappings().first()
        if row is None:
            return None
        return TripSummary(
            trip_id=row["id"],
            trip_code=row["code"],
            vehicle_code=row["vehicle_code"],
            driver_name=row["driver_name"],
            trip_status=row["status"],
        )
