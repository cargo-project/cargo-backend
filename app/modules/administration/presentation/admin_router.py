"""Consola del administrador: resumen del sistema y bitácora de actividad (solo ADMIN)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from app.composition import administration_factory
from app.core.http.dependencies import ScopeDep
from app.core.http.envelope import ERROR_RESPONSES, CamelModel, DataEnvelope, wrap
from app.modules.administration.application.admin_dto import ActivityEntry, AdminOverview
from app.modules.identity.presentation.api.auth_dependencies import AdminUser

admin_router = APIRouter(prefix="/admin", tags=["admin"], responses=ERROR_RESPONSES)

ActivityCategory = Literal["all", "auth", "users", "fleet", "trips", "notifications", "settings"]


class AccountSchema(CamelModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    failed_logins_last_day: int
    locked_until: datetime | None
    telegram_chat_id: str | None = None


class FleetSchema(CamelModel):
    vehicles: int
    drivers: int
    devices: int
    devices_online: int
    active_trips: int
    total_trips: int


class TelemetrySchema(CamelModel):
    total: int
    live: int
    delayed: int


class NotificationsSchema(CamelModel):
    sent: int
    failed: int
    pending: int
    skipped: int


class OverviewSchema(CamelModel):
    generated_at: datetime
    accounts: list[AccountSchema]
    logins_last_day: int
    failed_logins_last_day: int
    fleet: FleetSchema
    telemetry_last_day: TelemetrySchema
    events_last_day: dict[str, int]
    events_last_week: dict[str, int]
    delayed_events_last_week: int
    notifications_last_day: NotificationsSchema
    outbox_pending: int

    @classmethod
    def from_view(cls, view: AdminOverview) -> OverviewSchema:
        return cls(
            generated_at=view.generated_at,
            accounts=[AccountSchema.model_validate(a, from_attributes=True) for a in view.accounts],
            logins_last_day=view.logins_last_day,
            failed_logins_last_day=view.failed_logins_last_day,
            fleet=FleetSchema.model_validate(view.fleet, from_attributes=True),
            telemetry_last_day=TelemetrySchema.model_validate(view.telemetry_last_day, from_attributes=True),
            events_last_day=view.events_last_day,
            events_last_week=view.events_last_week,
            delayed_events_last_week=view.delayed_events_last_week,
            notifications_last_day=NotificationsSchema.model_validate(
                view.notifications_last_day, from_attributes=True
            ),
            outbox_pending=view.outbox_pending,
        )


class ActivitySchema(CamelModel):
    id: uuid.UUID
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: str
    actor_email: str | None
    actor_name: str | None
    details: dict[str, Any]

    @classmethod
    def from_entry(cls, entry: ActivityEntry) -> ActivitySchema:
        return cls.model_validate(entry, from_attributes=True)


@admin_router.get("/overview", summary="Platform status for the administrator (ADMIN)")
async def admin_overview(_: AdminUser, scope: ScopeDep) -> DataEnvelope[OverviewSchema]:
    view = await administration_factory.admin_overview(scope).execute()
    return wrap(OverviewSchema.from_view(view))


@admin_router.get("/activity", summary="Audit log: logins, account and data changes (ADMIN)")
async def admin_activity(
    _: AdminUser,
    scope: ScopeDep,
    category: ActivityCategory = "all",
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DataEnvelope[list[ActivitySchema]]:
    entries = await administration_factory.list_activity(scope).execute(category=category, before=before, limit=limit)
    return wrap([ActivitySchema.from_entry(e) for e in entries])
