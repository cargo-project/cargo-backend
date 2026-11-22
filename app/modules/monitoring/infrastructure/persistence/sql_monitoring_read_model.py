from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import RowMapping, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.monitoring.application.dto.monitoring_dto import (
    DashboardCounters,
    DashboardVehicleRow,
    MonitoringEventView,
    NotificationTrace,
    RecentActivity,
    TelemetryView,
    TrackView,
)
from app.modules.monitoring.application.monitoring_event_describer import MonitoringEventDescriber

_EVENTS_SQL = """
SELECT e.id, e.event_type, e.severity, e.status, e.started_at, e.event_time, e.detected_at,
       e.registered_at, ST_Y(e.position) AS latitude, ST_X(e.position) AS longitude, e.details,
       e.reviewed_at, t.code AS trip_code, v.code AS vehicle_code,
       d.first_name || ' ' || d.last_name AS driver_name
FROM monitoring_events e
JOIN trips t ON t.id = e.trip_id
JOIN vehicles v ON v.id = t.vehicle_id
JOIN drivers d ON d.id = t.driver_id
WHERE (CAST(:trip_code AS text) IS NULL OR t.code = :trip_code)
  AND (CAST(:status AS text) IS NULL OR e.status = :status)
  AND (CAST(:event_type AS text) IS NULL OR e.event_type = :event_type)
  AND (CAST(:event_id AS uuid) IS NULL OR e.id = :event_id)
ORDER BY e.detected_at DESC
LIMIT :limit
"""

_TELEMETRY_COLUMNS = """
te.message_id, dev.code AS device_code, t.code AS trip_code, te.sequence, te.event_time, te.received_at,
te.latitude, te.longitude, te.speed_kmh, te.kind, te.temporal_classification,
te.moving_away_m, te.distance_to_destination_m, COALESCE(te.inside_destination, FALSE) AS inside_destination
"""

# _TELEMETRY_COLUMNS es una lista fija de columnas; lo que manda el usuario va solo como parámetro.
_EVIDENCE_SQL = text(
    f"""
    SELECT ev.monitoring_event_id, {_TELEMETRY_COLUMNS}
    FROM monitoring_event_evidence ev
    JOIN telemetry_events te ON te.id = ev.telemetry_id
    JOIN iot_devices dev ON dev.id = te.device_id
    JOIN trips t ON t.id = te.trip_id
    WHERE ev.monitoring_event_id = ANY(:ids)
    ORDER BY te.sequence
    """  # noqa: S608
).bindparams(bindparam("ids", type_=ARRAY(UUID(as_uuid=True))))

_NOTIFICATIONS_SQL = text(
    """
    SELECT n.monitoring_event_id, r.name, n.status, n.attempts, n.attempted_at, n.sent_at, n.error
    FROM notifications n JOIN notification_recipients r ON r.id = n.recipient_id
    WHERE n.monitoring_event_id = ANY(:ids)
    ORDER BY r.name
    """
).bindparams(bindparam("ids", type_=ARRAY(UUID(as_uuid=True))))

_DASHBOARD_SQL = text(
    """
    SELECT v.code AS vehicle_code, v.plate, d.first_name || ' ' || d.last_name AS driver_name,
           t.origin_label, t.destination_label,
           COALESCE(last.latitude, ST_Y(t.origin)) AS latitude,
           COALESCE(last.longitude, ST_X(t.origin)) AS longitude,
           last.speed_kmh, dev.last_connection_at AS last_signal_at,
           EXISTS (SELECT 1 FROM monitoring_events me
                    WHERE me.trip_id = t.id AND me.status = 'pending'
                      AND me.event_type IN ('ROUTE_DEVIATION', 'PROLONGED_STOP', 'EMERGENCY', 'CONNECTION_LOSS'))
             AS has_pending_alert,
           (t.monitoring_configuration ->> 'connection_loss_seconds')::int AS connection_loss_seconds,
           (t.monitoring_configuration ->> 'stop_speed_kmh')::float AS stop_speed_kmh
    FROM trips t
    JOIN vehicles v ON v.id = t.vehicle_id
    JOIN drivers d ON d.id = t.driver_id
    LEFT JOIN iot_devices dev ON dev.id = t.device_id
    LEFT JOIN LATERAL (
        SELECT te.latitude, te.longitude, te.speed_kmh FROM telemetry_events te
        WHERE te.trip_id = t.id ORDER BY te.event_time DESC LIMIT 1
    ) last ON TRUE
    WHERE t.status = 'ongoing'
    ORDER BY v.code
    """
)

_COUNTERS_SQL = text(
    """
    SELECT (SELECT count(*) FROM vehicles) AS vehicles,
           (SELECT count(*) FROM trips WHERE status = 'ongoing') AS ongoing_trips,
           (SELECT count(*) FROM monitoring_events WHERE status = 'pending') AS pending_alerts,
           (SELECT count(*) FROM iot_devices
             WHERE is_active AND device_type = 'edge_gateway'
               AND (last_connection_at IS NULL OR last_connection_at < :online_since)) AS offline_devices
    """
)

_RECENT_SQL = text(
    """
    SELECT e.id, e.detected_at, e.event_type, v.code AS vehicle_code
    FROM monitoring_events e JOIN trips t ON t.id = e.trip_id JOIN vehicles v ON v.id = t.vehicle_id
    ORDER BY e.detected_at DESC LIMIT :limit
    """
)


def _telemetry(row: RowMapping) -> TelemetryView:
    return TelemetryView(
        message_id=row["message_id"],
        device_code=row["device_code"],
        trip_code=row["trip_code"],
        sequence=row["sequence"],
        event_time=row["event_time"],
        received_at=row["received_at"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        speed_kmh=row["speed_kmh"],
        kind=row["kind"],
        temporal_classification=row["temporal_classification"],
        moving_away_m=row["moving_away_m"],
        distance_to_destination_m=row["distance_to_destination_m"],
        inside_destination=row["inside_destination"],
    )


class SqlMonitoringReadModel:
    def __init__(self, session: AsyncSession, describer: MonitoringEventDescriber | None = None) -> None:
        self._session = session
        self._describer = describer or MonitoringEventDescriber()

    async def list_events(
        self, *, trip_code: str | None, status: str | None, event_type: str | None, limit: int
    ) -> list[MonitoringEventView]:
        return await self._events(
            {"trip_code": trip_code, "status": status, "event_type": event_type, "event_id": None, "limit": limit}
        )

    async def get_event(self, event_id: uuid.UUID) -> MonitoringEventView | None:
        events = await self._events(
            {"trip_code": None, "status": None, "event_type": None, "event_id": event_id, "limit": 1}
        )
        return events[0] if events else None

    async def _events(self, params: dict[str, Any]) -> list[MonitoringEventView]:
        rows = list((await self._session.execute(text(_EVENTS_SQL), params)).mappings())
        if not rows:
            return []
        ids = [row["id"] for row in rows]
        evidence: dict[uuid.UUID, list[TelemetryView]] = defaultdict(list)
        for row in (await self._session.execute(_EVIDENCE_SQL, {"ids": ids})).mappings():
            evidence[row["monitoring_event_id"]].append(_telemetry(row))
        notifications: dict[uuid.UUID, list[NotificationTrace]] = defaultdict(list)
        for row in (await self._session.execute(_NOTIFICATIONS_SQL, {"ids": ids})).mappings():
            notifications[row["monitoring_event_id"]].append(
                NotificationTrace(
                    recipient_name=row["name"],
                    status=row["status"],
                    attempts=row["attempts"],
                    attempted_at=row["attempted_at"],
                    sent_at=row["sent_at"],
                    error=row["error"],
                )
            )
        return [
            MonitoringEventView(
                id=row["id"],
                event_type=row["event_type"],
                severity=row["severity"],
                status=row["status"],
                trip_code=row["trip_code"],
                vehicle_code=row["vehicle_code"],
                driver_name=row["driver_name"],
                started_at=row["started_at"],
                event_time=row["event_time"],
                detected_at=row["detected_at"],
                registered_at=row["registered_at"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                details=dict(row["details"] or {}),
                description=self._describer.describe(row["event_type"], dict(row["details"] or {})),
                reviewed_at=row["reviewed_at"],
                evidence=evidence[row["id"]],
                notifications=notifications[row["id"]],
            )
            for row in rows
        ]

    async def track(self, trip_code: str) -> TrackView | None:
        exists = await self._session.scalar(text("SELECT id FROM trips WHERE code = :code"), {"code": trip_code})
        if exists is None:
            return None
        rows = await self._session.execute(
            text(
                "SELECT longitude, latitude FROM telemetry_events "
                "WHERE trip_id = :trip_id ORDER BY event_time, sequence"
            ),
            {"trip_id": exists},
        )
        return TrackView(trip_code=trip_code, coordinates=[(float(r[0]), float(r[1])) for r in rows])

    async def telemetry(self, trip_code: str, *, limit: int, before: datetime | None) -> list[TelemetryView]:
        rows = await self._session.execute(
            text(
                f"""
                SELECT {_TELEMETRY_COLUMNS}
                FROM telemetry_events te
                JOIN iot_devices dev ON dev.id = te.device_id
                JOIN trips t ON t.id = te.trip_id
                WHERE t.code = :code AND (CAST(:before AS timestamptz) IS NULL OR te.event_time < :before)
                ORDER BY te.event_time DESC
                LIMIT :limit
                """  # noqa: S608
            ),
            {"code": trip_code, "before": before, "limit": limit},
        )
        return [_telemetry(row) for row in rows.mappings()]

    async def dashboard_rows(self) -> list[DashboardVehicleRow]:
        rows = await self._session.execute(_DASHBOARD_SQL)
        return [
            DashboardVehicleRow(
                vehicle_code=r["vehicle_code"],
                plate=r["plate"],
                driver_name=r["driver_name"],
                origin_label=r["origin_label"],
                destination_label=r["destination_label"],
                latitude=float(r["latitude"]),
                longitude=float(r["longitude"]),
                speed_kmh=r["speed_kmh"],
                last_signal_at=r["last_signal_at"],
                has_pending_alert=r["has_pending_alert"],
                connection_loss_seconds=r["connection_loss_seconds"],
                stop_speed_kmh=r["stop_speed_kmh"],
            )
            for r in rows.mappings()
        ]

    async def dashboard_counters(self, *, now: datetime, online_window: timedelta) -> DashboardCounters:
        row = (await self._session.execute(_COUNTERS_SQL, {"online_since": now - online_window})).mappings().one()
        return DashboardCounters(
            vehicles=row["vehicles"],
            ongoing_trips=row["ongoing_trips"],
            pending_alerts=row["pending_alerts"],
            offline_devices=row["offline_devices"],
        )

    async def recent_activity(self, limit: int) -> list[RecentActivity]:
        rows = await self._session.execute(_RECENT_SQL, {"limit": limit})
        return [
            RecentActivity(
                event_id=r["id"],
                detected_at=r["detected_at"],
                event_type=r["event_type"],
                vehicle_code=r["vehicle_code"],
            )
            for r in rows.mappings()
        ]
