"""Contratos HTTP de alertas, historial de telemetría, trayecto y dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from app.core.http.envelope import CamelModel
from app.modules.monitoring.application.dto.monitoring_dto import (
    DashboardView,
    MonitoringEventView,
    TelemetryView,
    TrackView,
)

# Las etiquetas del dashboard son textos que el frontend compara tal cual (dashboardService.ts).
_SITUATION_LABELS = {
    "alert": "Alerta",
    "no_connection": "Sin conexión",
    "stopped": "Detenido",
    "on_route": "En ruta",
}


class TelemetryResponse(CamelModel):
    """ApiTelemetry (+ temporalClassification y movingAwayM)."""

    event_id: uuid.UUID
    device_code: str
    trip_code: str
    sequence_number: int
    event_time: datetime
    received_at: datetime
    latitude: float
    longitude: float
    speed_kmh: float
    kind: Literal["POSITION", "EMERGENCY"]
    retransmitted: bool
    temporal_classification: Literal["LIVE", "DELAYED"]
    distance_to_destination_m: float
    moving_away_m: float | None = None  # cuánto se pasó del punto más cercano al destino
    inside_arrival_area: bool

    @classmethod
    def from_view(cls, view: TelemetryView) -> TelemetryResponse:
        return cls(
            event_id=view.message_id,
            device_code=view.device_code,
            trip_code=view.trip_code,
            sequence_number=view.sequence,
            event_time=view.event_time,
            received_at=view.received_at,
            latitude=view.latitude,
            longitude=view.longitude,
            speed_kmh=view.speed_kmh,
            kind=view.kind,
            retransmitted=view.temporal_classification == "DELAYED",
            temporal_classification=view.temporal_classification,
            distance_to_destination_m=view.distance_to_destination_m or 0.0,
            moving_away_m=view.moving_away_m,
            inside_arrival_area=view.inside_destination,
        )


class NotificationTraceResponse(CamelModel):
    recipient_name: str
    status: str
    attempts: int
    attempted_at: datetime | None
    sent_at: datetime | None
    error: str | None


class MonitoringEventResponse(CamelModel):
    """ApiMonitoringEvent (+ severity, registeredAt, reviewedAt y notifications)."""

    id: uuid.UUID
    type: str
    severity: str
    trip_code: str
    vehicle_code: str
    driver_name: str
    started_at: datetime | None = None
    event_time: datetime
    detected_at: datetime
    registered_at: datetime
    latitude: float | None = None
    longitude: float | None = None
    description: str
    details: dict[str, Any]
    status: Literal["pending", "reviewed"]
    reviewed_at: datetime | None = None
    evidence: list[TelemetryResponse]
    notifications: list[NotificationTraceResponse]

    @classmethod
    def from_view(cls, view: MonitoringEventView) -> MonitoringEventResponse:
        return cls(
            id=view.id,
            type=view.event_type,
            severity=view.severity,
            trip_code=view.trip_code,
            vehicle_code=view.vehicle_code,
            driver_name=view.driver_name,
            started_at=view.started_at,
            event_time=view.event_time,
            detected_at=view.detected_at,
            registered_at=view.registered_at,
            latitude=view.latitude,
            longitude=view.longitude,
            description=view.description,
            details=view.details,
            status=view.status,
            reviewed_at=view.reviewed_at,
            evidence=[TelemetryResponse.from_view(item) for item in view.evidence],
            notifications=[NotificationTraceResponse.model_validate(n) for n in view.notifications],
        )


class TrackResponse(CamelModel):
    """ApiTrack: Feature GeoJSON (lon, lat)."""

    type: Literal["Feature"] = "Feature"
    properties: dict[str, Any]
    geometry: dict[str, Any]

    @classmethod
    def from_view(cls, view: TrackView) -> TrackResponse:
        return cls(
            properties={"tripId": view.trip_code, "pointCount": len(view.coordinates)},
            geometry={"type": "LineString", "coordinates": [list(c) for c in view.coordinates]},
        )


class DashboardStat(CamelModel):
    id: str
    value: int


class DashboardVehicle(CamelModel):
    id: str
    plate: str
    driver: str
    status: str
    speed: float | None = None
    origin: str
    destination: str
    last_signal_at: datetime | None = None
    latitude: float
    longitude: float


class DashboardActivity(CamelModel):
    id: str
    time: datetime
    type: str
    vehicle_id: str


class DashboardResponse(CamelModel):
    """ApiDashboard."""

    stats: list[DashboardStat]
    vehicles: list[DashboardVehicle]
    recent_activity: list[DashboardActivity]

    @classmethod
    def from_view(cls, view: DashboardView) -> DashboardResponse:
        counters = view.counters
        return cls(
            stats=[
                DashboardStat(id="active", value=counters.vehicles),
                DashboardStat(id="trips", value=counters.ongoing_trips),
                DashboardStat(id="alerts", value=counters.pending_alerts),
                DashboardStat(id="offline", value=counters.offline_devices),
            ],
            vehicles=[
                DashboardVehicle(
                    id=v.vehicle_code,
                    plate=v.plate,
                    driver=v.driver_name,
                    status=_SITUATION_LABELS[v.situation],
                    speed=v.speed_kmh,
                    origin=v.origin_label,
                    destination=v.destination_label,
                    last_signal_at=v.last_signal_at,
                    latitude=v.latitude,
                    longitude=v.longitude,
                )
                for v in view.vehicles
            ],
            recent_activity=[
                DashboardActivity(id=str(a.event_id), time=a.detected_at, type=a.event_type, vehicle_id=a.vehicle_code)
                for a in view.recent_activity
            ],
        )
