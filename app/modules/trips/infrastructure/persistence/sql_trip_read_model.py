from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trips.application.dto.trip_dto import RecipientView, TripView
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration

_TRIPS_SQL = """
SELECT t.id, t.code, t.status, t.origin_label, ST_Y(t.origin) AS origin_lat, ST_X(t.origin) AS origin_lon,
       t.destination_label, ST_Y(t.destination) AS destination_lat, ST_X(t.destination) AS destination_lon,
       t.cargo_description, t.planned_start_at, t.started_at, t.completed_at, t.cancelled_at,
       t.monitoring_configuration, t.created_at,
       v.code AS vehicle_code, v.plate, d.code AS driver_code, d.first_name || ' ' || d.last_name AS driver_name,
       c.name AS client_name,
       ST_Distance(t.origin::geography, t.destination::geography) AS direct_distance_m,
       (SELECT te.distance_to_destination_m FROM telemetry_events te
         WHERE te.trip_id = t.id AND te.distance_to_destination_m IS NOT NULL
         ORDER BY te.event_time DESC LIMIT 1) AS latest_distance_to_destination_m,
       COALESCE((SELECT json_agg(json_build_object(
                    'id', r.id, 'name', r.name, 'chat', r.telegram_chat_id,
                    'active', r.is_active AND r.deleted_at IS NULL) ORDER BY r.name)
                 FROM trip_notification_recipients tr
                 JOIN notification_recipients r ON r.id = tr.recipient_id
                 WHERE tr.trip_id = t.id), '[]'::json) AS recipients
FROM trips t
JOIN vehicles v ON v.id = t.vehicle_id
JOIN drivers d ON d.id = t.driver_id
LEFT JOIN clients c ON c.id = t.client_id
"""


def _progress(row: RowMapping) -> int:
    """Cuánto se acercó al destino: 1 - (distancia actual / distancia origen-destino).

    Como no hay ruta, el avance es cuánto se acortó la distancia en línea recta.
    Se queda en 99 hasta que el viaje termina (llegada confirmada por CEP).
    """
    if row["status"] == "completed":
        return 100
    remaining, direct = row["latest_distance_to_destination_m"], row["direct_distance_m"]
    if row["status"] == "configured" or remaining is None or not direct:
        return 0
    return max(0, min(99, round((1 - float(remaining) / float(direct)) * 100)))


def _recipients(raw: Any) -> list[RecipientView]:
    items = json.loads(raw) if isinstance(raw, str) else raw
    return [
        RecipientView(
            id=uuid.UUID(str(item["id"])), name=item["name"], telegram_chat_id=item["chat"], active=bool(item["active"])
        )
        for item in items
    ]


def _trip(row: RowMapping) -> TripView:
    return TripView(
        id=row["id"],
        code=row["code"],
        vehicle_code=row["vehicle_code"],
        plate=row["plate"],
        driver_code=row["driver_code"],
        driver_name=row["driver_name"],
        origin_label=row["origin_label"],
        origin_latitude=row["origin_lat"],
        origin_longitude=row["origin_lon"],
        destination_label=row["destination_label"],
        destination_latitude=row["destination_lat"],
        destination_longitude=row["destination_lon"],
        cargo_description=row["cargo_description"],
        status=row["status"],
        planned_start_at=row["planned_start_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        cancelled_at=row["cancelled_at"],
        progress=_progress(row),
        monitoring_configuration=MonitoringConfiguration.from_stored(row["monitoring_configuration"]),
        direct_distance_m=float(row["direct_distance_m"]),
        client_name=row["client_name"],
        recipients=_recipients(row["recipients"]),
    )


class SqlTripReadModel:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_trips(self) -> list[TripView]:
        rows = await self._session.execute(text(_TRIPS_SQL + " ORDER BY t.created_at DESC"))
        return [_trip(row) for row in rows.mappings()]

    async def get_trip(self, code: str) -> TripView | None:
        rows = await self._session.execute(text(_TRIPS_SQL + " WHERE t.code = :code"), {"code": code})
        row = rows.mappings().first()
        return _trip(row) if row else None
