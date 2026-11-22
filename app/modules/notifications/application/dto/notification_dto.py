from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EventNotificationRequest:
    """Lo que el contexto de notificaciones necesita saber de un evento detectado."""

    monitoring_event_id: uuid.UUID
    trip_id: uuid.UUID
    trip_code: str
    vehicle_code: str
    event_type: str
    severity: str
    description: str
    detected_at: datetime
    latitude: float | None = None
    longitude: float | None = None
    driver_name: str | None = None
    # Alerta de algo que pasó mientras no había señal (se detectó al reconectar).
    delayed: bool = False
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DispatchSummary:
    sent: int
    failed: int
    skipped: int
    already_handled: int
