"""AdminReadModel con consultas SQL de solo lectura sobre todas las tablas (vista transversal del sistema)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.administration.application.admin_dto import (
    AccountActivity,
    ActivityEntry,
    AdminOverview,
    FleetCounts,
    NotificationCounts,
    TelemetryCounts,
)

_ACCOUNTS = text(
    """
    SELECT u.id, u.email, u.full_name, u.role, u.is_active, u.created_at, u.locked_until, u.telegram_chat_id,
           (SELECT max(a.occurred_at) FROM audit_log a
             WHERE a.action = 'user.login' AND a.entity_id = u.id::text) AS last_login_at,
           (SELECT count(*) FROM audit_log a
             WHERE a.action = 'user.login_failed' AND a.entity_id = u.id::text AND a.occurred_at >= :day) AS failed_24h
      FROM users u
     ORDER BY u.role, u.full_name
    """
)

_COUNTS = text(
    """
    SELECT
      (SELECT count(*) FROM audit_log WHERE action = 'user.login' AND occurred_at >= :day) AS logins,
      (SELECT count(*) FROM audit_log WHERE action = 'user.login_failed' AND occurred_at >= :day) AS failed_logins,
      (SELECT count(*) FROM vehicles) AS vehicles,
      (SELECT count(*) FROM drivers) AS drivers,
      (SELECT count(*) FROM iot_devices) AS devices,
      (SELECT count(*) FROM iot_devices WHERE is_active AND last_connection_at >= :online_since) AS devices_online,
      (SELECT count(*) FROM trips WHERE status = 'ongoing') AS active_trips,
      (SELECT count(*) FROM trips) AS total_trips,
      (SELECT count(*) FROM telemetry_events WHERE received_at >= :day) AS telemetry,
      (SELECT count(*) FROM telemetry_events WHERE received_at >= :day AND temporal_classification = 'LIVE') AS live,
      (SELECT count(*) FROM telemetry_events WHERE received_at >= :day AND temporal_classification = 'DELAYED')
        AS delayed,
      (SELECT count(*) FROM monitoring_events WHERE detected_at >= :week AND (details->>'delayed')::boolean)
        AS delayed_events,
      (SELECT count(*) FROM notifications WHERE created_at >= :day AND status = 'sent') AS sent,
      (SELECT count(*) FROM notifications WHERE created_at >= :day AND status = 'failed') AS failed,
      (SELECT count(*) FROM notifications WHERE created_at >= :day AND status = 'pending') AS pending,
      (SELECT count(*) FROM notifications WHERE created_at >= :day AND status = 'skipped') AS skipped,
      (SELECT count(*) FROM integration_outbox) AS outbox
    """
)

_EVENTS_BY_TYPE = text("SELECT event_type, count(*) FROM monitoring_events WHERE detected_at >= :since GROUP BY 1")


class SqlAdminReadModel:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _events_by_type(self, since: datetime) -> dict[str, int]:
        rows = await self._session.execute(_EVENTS_BY_TYPE, {"since": since})
        return {str(event_type): int(count) for event_type, count in rows}

    async def overview(self, *, now: datetime, online_window_seconds: int) -> AdminOverview:
        day, week = now - timedelta(days=1), now - timedelta(days=7)
        accounts = [
            AccountActivity(
                id=r.id,
                email=r.email,
                full_name=r.full_name,
                role=r.role,
                is_active=r.is_active,
                created_at=r.created_at,
                last_login_at=r.last_login_at,
                failed_logins_last_day=int(r.failed_24h),
                locked_until=r.locked_until if r.locked_until and r.locked_until > now else None,
                telegram_chat_id=r.telegram_chat_id,
            )
            for r in await self._session.execute(_ACCOUNTS, {"day": day})
        ]
        c = (
            await self._session.execute(
                _COUNTS, {"day": day, "week": week, "online_since": now - timedelta(seconds=online_window_seconds)}
            )
        ).one()
        return AdminOverview(
            generated_at=now,
            accounts=accounts,
            logins_last_day=int(c.logins),
            failed_logins_last_day=int(c.failed_logins),
            fleet=FleetCounts(
                vehicles=int(c.vehicles),
                drivers=int(c.drivers),
                devices=int(c.devices),
                devices_online=int(c.devices_online),
                active_trips=int(c.active_trips),
                total_trips=int(c.total_trips),
            ),
            telemetry_last_day=TelemetryCounts(total=int(c.telemetry), live=int(c.live), delayed=int(c.delayed)),
            events_last_day=await self._events_by_type(day),
            events_last_week=await self._events_by_type(week),
            delayed_events_last_week=int(c.delayed_events),
            notifications_last_day=NotificationCounts(
                sent=int(c.sent), failed=int(c.failed), pending=int(c.pending), skipped=int(c.skipped)
            ),
            outbox_pending=int(c.outbox),
        )

    async def activity(
        self, *, action_prefixes: tuple[str, ...] | None, before: datetime | None, limit: int
    ) -> list[ActivityEntry]:
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if before is not None:
            conditions.append("a.occurred_at < :before")
            params["before"] = before
        if action_prefixes:
            likes = []
            for index, prefix in enumerate(action_prefixes):
                params[f"p{index}"] = prefix if not prefix.endswith(".") else prefix + "%"
                likes.append(f"a.action {'LIKE' if prefix.endswith('.') else '='} :p{index}")
            conditions.append("(" + " OR ".join(likes) + ")")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = text(
            f"""
            SELECT a.id, a.occurred_at, a.action, a.entity_type, a.entity_id, a.details,
                   u.email AS actor_email, u.full_name AS actor_name
              FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id
              {where}
             ORDER BY a.occurred_at DESC
             LIMIT :limit
            """  # noqa: S608 - solo se interpolan condiciones fijas; los valores van como parámetros
        )
        rows = await self._session.execute(sql, params)
        return [
            ActivityEntry(
                id=r.id,
                occurred_at=r.occurred_at,
                action=r.action,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                actor_email=r.actor_email,
                actor_name=r.actor_name,
                details=dict(r.details or {}),
            )
            for r in rows
        ]
