from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.modules.monitoring.domain.exceptions.monitoring_errors import (
    InvalidDetectedEventError,
    MonitoringEventAlreadyReviewedError,
)
from app.shared.domain.entity import Entity
from app.shared.domain.geo_point import GeoPoint


class MonitoringEventType(StrEnum):
    ROUTE_DEVIATION = "ROUTE_DEVIATION"
    PROLONGED_STOP = "PROLONGED_STOP"
    CONNECTION_LOSS = "CONNECTION_LOSS"
    DESTINATION_ARRIVAL = "DESTINATION_ARRIVAL"
    EMERGENCY = "EMERGENCY"
    TRIP_STARTED = "TRIP_STARTED"  # hito del ciclo de vida (no lo detecta CEP)


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    INFO = "INFO"


class MonitoringEventStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"


# La severidad es regla de negocio según el tipo de evento, no la decide CEP.
_SEVERITY_BY_TYPE: dict[MonitoringEventType, Severity] = {
    MonitoringEventType.EMERGENCY: Severity.CRITICAL,
    MonitoringEventType.ROUTE_DEVIATION: Severity.HIGH,
    MonitoringEventType.CONNECTION_LOSS: Severity.HIGH,
    MonitoringEventType.PROLONGED_STOP: Severity.MEDIUM,
    MonitoringEventType.DESTINATION_ARRIVAL: Severity.INFO,
    MonitoringEventType.TRIP_STARTED: Severity.INFO,
}


@dataclass(frozen=True, slots=True)
class MonitoringEventEvidence:
    """Enlace a una lectura de telemetría que respalda la detección."""

    telemetry_id: uuid.UUID
    sequence: int


@dataclass(eq=False)
class MonitoringEvent(Entity):
    """Situación relevante que CEP detecta a partir de una o varias lecturas (o de su ausencia),
    o un hito del viaje del que hay que avisar al operador (TRIP_STARTED).

    El id lo genera CEP (o se calcula a partir del viaje en los hitos), así el registro es
    idempotente frente a reentregas QoS 1, reanuncios periódicos y los dos consumidores
    (API y servicio de notificaciones).
    """

    id: uuid.UUID
    trip_id: uuid.UUID
    event_type: MonitoringEventType
    severity: Severity
    status: MonitoringEventStatus
    event_time: datetime
    detected_at: datetime
    registered_at: datetime
    started_at: datetime | None = None
    position: GeoPoint | None = None
    details: dict[str, Any] = field(default_factory=dict)
    evidence: tuple[MonitoringEventEvidence, ...] = ()
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None

    @classmethod
    def detect(
        cls,
        *,
        event_id: uuid.UUID,
        trip_id: uuid.UUID,
        event_type: str,
        event_time: datetime,
        detected_at: datetime,
        registered_at: datetime,
        started_at: datetime | None,
        position: GeoPoint | None,
        details: dict[str, Any],
        evidence: tuple[MonitoringEventEvidence, ...],
    ) -> MonitoringEvent:
        try:
            parsed_type = MonitoringEventType(event_type)
        except ValueError as error:
            raise InvalidDetectedEventError(f"Tipo de evento desconocido: {event_type}") from error
        if started_at is not None and started_at > event_time:
            raise InvalidDetectedEventError("El inicio de la condición es posterior al evento.")
        return cls(
            id=event_id,
            trip_id=trip_id,
            event_type=parsed_type,
            severity=_SEVERITY_BY_TYPE[parsed_type],
            status=MonitoringEventStatus.PENDING,
            event_time=event_time,
            detected_at=detected_at,
            registered_at=registered_at,
            started_at=started_at,
            position=position,
            details=details,
            evidence=evidence,
        )

    @property
    def detection_latency_seconds(self) -> float:
        """event_time -> detected_at; es un KPI para la evaluación del proyecto."""
        return (self.detected_at - self.event_time).total_seconds()

    def acknowledge(self, *, user_id: uuid.UUID, now: datetime) -> None:
        if self.status == MonitoringEventStatus.REVIEWED:
            raise MonitoringEventAlreadyReviewedError("El evento ya fue revisado.")
        self.status = MonitoringEventStatus.REVIEWED
        self.reviewed_by = user_id
        self.reviewed_at = now
