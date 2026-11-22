from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.modules.monitoring.domain.exceptions.monitoring_errors import (
    TelemetryRejectedError,
    TelemetryRejectionReason,
)

ONGOING = "ongoing"
CONFIGURED = "configured"


@dataclass(frozen=True, slots=True)
class TelemetryTripContext:
    """Foto de los datos del dispositivo y del viaje que hacen falta para validar una lectura."""

    device_id: uuid.UUID
    device_code: str
    device_active: bool
    trip_id: uuid.UUID | None
    trip_code: str | None
    vehicle_code: str | None
    trip_status: str | None
    trip_device_id: uuid.UUID | None
    trip_started_at: datetime | None
    trip_ended_at: datetime | None

    @property
    def trip_is_ongoing(self) -> bool:
        return self.trip_status == ONGOING


class TelemetryAcceptancePolicy:
    """Validación de negocio de una lectura contra el estado del dispositivo y del viaje.

    grace tolera pequeñas diferencias de reloj entre el vehículo y la plataforma al
    inicio y fin del viaje; max_future_skew rechaza marcas de tiempo del futuro.
    """

    def __init__(self, *, max_future_skew: timedelta, grace: timedelta = timedelta(minutes=5)) -> None:
        self._max_future_skew = max_future_skew
        self._grace = grace

    def ensure_acceptable(self, context: TelemetryTripContext, *, event_time: datetime, now: datetime) -> None:
        if not context.device_active:
            raise TelemetryRejectedError(TelemetryRejectionReason.DEVICE_INACTIVE, "Dispositivo inactivo.")
        if context.trip_id is None or context.trip_status is None:
            raise TelemetryRejectedError(TelemetryRejectionReason.UNKNOWN_TRIP, "Viaje desconocido.")
        if context.trip_device_id != context.device_id:
            raise TelemetryRejectedError(
                TelemetryRejectionReason.DEVICE_TRIP_MISMATCH,
                "El dispositivo no es el asignado al viaje.",
            )
        if context.trip_status == CONFIGURED or context.trip_started_at is None:
            raise TelemetryRejectedError(TelemetryRejectionReason.TRIP_NOT_STARTED, "El viaje no ha iniciado.")
        if event_time > now + self._max_future_skew:
            raise TelemetryRejectedError(
                TelemetryRejectionReason.FUTURE_TIMESTAMP, "La marca de tiempo está en el futuro."
            )
        if event_time < context.trip_started_at - self._grace:
            raise TelemetryRejectedError(
                TelemetryRejectionReason.BEFORE_TRIP_START, "Medición anterior al inicio del viaje."
            )
        if context.trip_ended_at is not None and event_time > context.trip_ended_at + self._grace:
            raise TelemetryRejectedError(
                TelemetryRejectionReason.AFTER_TRIP_END, "Medición posterior al fin del viaje."
            )
