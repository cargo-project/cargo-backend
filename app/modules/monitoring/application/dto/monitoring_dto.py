from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


@dataclass(frozen=True, slots=True)
class RawTelemetryCommand:
    """Mensaje de telemetría tal como llega del broker IoT, ya parseado."""

    topic_device_code: str
    message_id: uuid.UUID
    device_code: str
    trip_id: uuid.UUID
    sequence: int
    event_time: datetime
    latitude: float
    longitude: float
    speed_kmh: float
    emergency: bool
    received_at: datetime


class IngestionOutcome(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class IngestionResult:
    outcome: IngestionOutcome
    telemetry_id: uuid.UUID | None = None
    temporal_classification: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedTelemetry:
    """Contenido de telemetry/normalized (lo que recibe el servicio geoespacial)."""

    telemetry_id: uuid.UUID
    trip_id: uuid.UUID
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DetectedEventCommand:
    """Contenido de events/detected que manda Siddhi (o un hito del viaje, ver trip_milestones)."""

    event_id: uuid.UUID
    event_type: str
    trip_id: uuid.UUID
    event_time: datetime
    detected_at: datetime
    started_at: datetime | None
    latitude: float | None
    longitude: float | None
    evidence_from_sequence: int | None
    evidence_to_sequence: int | None
    metric_value: float | None
    delayed: bool = False
    extra_details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TripSummary:
    trip_id: uuid.UUID
    trip_code: str
    vehicle_code: str
    driver_name: str
    trip_status: str


@dataclass(frozen=True, slots=True)
class RegisteredEvent:
    event_id: uuid.UUID
    created: bool
    trip: TripSummary
    event_type: str
    severity: str
    description: str
    detected_at: datetime
    latitude: float | None
    longitude: float | None
    # True si ocurrió mientras no había señal y se detectó al reconectar.
    delayed: bool = False
    # Cuándo empezó a pasar (inicio del episodio) o, si no aplica, cuándo pasó.
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TelemetryView:
    message_id: uuid.UUID
    device_code: str
    trip_code: str
    sequence: int
    event_time: datetime
    received_at: datetime
    latitude: float
    longitude: float
    speed_kmh: float
    kind: str
    temporal_classification: str
    moving_away_m: float | None
    distance_to_destination_m: float | None
    inside_destination: bool


@dataclass(frozen=True, slots=True)
class NotificationTrace:
    recipient_name: str
    status: str
    attempts: int
    attempted_at: datetime | None
    sent_at: datetime | None
    error: str | None


@dataclass(frozen=True, slots=True)
class MonitoringEventView:
    id: uuid.UUID
    event_type: str
    severity: str
    status: str
    trip_code: str
    vehicle_code: str
    driver_name: str
    started_at: datetime | None
    event_time: datetime
    detected_at: datetime
    registered_at: datetime
    latitude: float | None
    longitude: float | None
    details: dict[str, Any]
    description: str
    reviewed_at: datetime | None
    evidence: list[TelemetryView] = field(default_factory=list)
    notifications: list[NotificationTrace] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TrackView:
    trip_code: str
    coordinates: list[tuple[float, float]]


@dataclass(frozen=True, slots=True)
class DashboardVehicleRow:
    vehicle_code: str
    plate: str
    driver_name: str
    origin_label: str
    destination_label: str
    latitude: float
    longitude: float
    speed_kmh: float | None
    last_signal_at: datetime | None
    has_pending_alert: bool
    connection_loss_seconds: int
    stop_speed_kmh: float


@dataclass(frozen=True, slots=True)
class DashboardCounters:
    vehicles: int
    ongoing_trips: int
    pending_alerts: int
    offline_devices: int


@dataclass(frozen=True, slots=True)
class RecentActivity:
    event_id: uuid.UUID
    detected_at: datetime
    event_type: str
    vehicle_code: str


@dataclass(frozen=True, slots=True)
class DashboardVehicleView:
    vehicle_code: str
    plate: str
    driver_name: str
    situation: str
    speed_kmh: float | None
    origin_label: str
    destination_label: str
    last_signal_at: datetime | None
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class DashboardView:
    counters: DashboardCounters
    vehicles: list[DashboardVehicleView]
    recent_activity: list[RecentActivity]
