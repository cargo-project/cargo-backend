from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AccountActivity:
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


@dataclass(frozen=True, slots=True)
class FleetCounts:
    vehicles: int
    drivers: int
    devices: int
    devices_online: int
    active_trips: int
    total_trips: int


@dataclass(frozen=True, slots=True)
class TelemetryCounts:
    total: int
    live: int
    delayed: int


@dataclass(frozen=True, slots=True)
class NotificationCounts:
    sent: int
    failed: int
    pending: int
    skipped: int


@dataclass(frozen=True, slots=True)
class AdminOverview:
    """Fotografía del sistema para el administrador (ventanas de 24 h y 7 días)."""

    generated_at: datetime
    accounts: list[AccountActivity]
    logins_last_day: int
    failed_logins_last_day: int
    fleet: FleetCounts
    telemetry_last_day: TelemetryCounts
    events_last_day: dict[str, int] = field(default_factory=dict)
    events_last_week: dict[str, int] = field(default_factory=dict)
    delayed_events_last_week: int = 0
    notifications_last_day: NotificationCounts = field(default_factory=lambda: NotificationCounts(0, 0, 0, 0))
    outbox_pending: int = 0


@dataclass(frozen=True, slots=True)
class ActivityEntry:
    id: uuid.UUID
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: str
    actor_email: str | None
    actor_name: str | None
    details: dict[str, Any]


# Categorías de la bitácora -> prefijos de acción del registro de auditoría.
ACTIVITY_CATEGORIES: dict[str, tuple[str, ...]] = {
    "auth": ("user.login", "user.login_failed", "user.password_changed"),
    "users": ("user.",),
    "fleet": ("vehicle.", "driver.", "device."),
    "trips": ("trip.", "monitoring_event."),
    "notifications": ("recipient.",),
    "settings": ("settings.", "geofence.", "client."),
}
