from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.modules.monitoring.domain.exceptions.monitoring_errors import (
    TelemetryRejectedError,
    TelemetryRejectionReason,
)
from app.modules.monitoring.domain.value_objects.spatial_context import SpatialContext
from app.modules.monitoring.domain.value_objects.temporal_classification import TemporalClassification
from app.shared.domain.entity import Entity
from app.shared.domain.geo_point import GeoPoint

MAX_PLAUSIBLE_SPEED_KMH = 250.0


class TelemetryKind(StrEnum):
    POSITION = "POSITION"
    EMERGENCY = "EMERGENCY"  # botón de pánico físico del dispositivo


@dataclass(eq=False)
class TelemetryEvent(Entity):
    """Una lectura inmutable que manda un dispositivo.

    Su identidad es message_id (se genera en el vehículo), así las reentregas QoS 1 y
    las retransmisiones del store-and-forward se reconocen como la misma lectura.
    event_time es cuándo pasó en el vehículo y nunca se pisa; received_at es cuándo
    lo recibió la plataforma.
    """

    id: uuid.UUID
    message_id: uuid.UUID
    device_id: uuid.UUID
    trip_id: uuid.UUID
    sequence: int
    event_time: datetime
    received_at: datetime
    position: GeoPoint
    speed_kmh: float
    kind: TelemetryKind
    temporal_classification: TemporalClassification
    spatial_context: SpatialContext | None = None
    enriched_at: datetime | None = None

    @classmethod
    def receive(
        cls,
        *,
        message_id: uuid.UUID,
        device_id: uuid.UUID,
        trip_id: uuid.UUID,
        sequence: int,
        event_time: datetime,
        received_at: datetime,
        position: GeoPoint,
        speed_kmh: float,
        kind: TelemetryKind,
        temporal_classification: TemporalClassification,
    ) -> TelemetryEvent:
        if sequence < 0:
            raise TelemetryRejectedError(TelemetryRejectionReason.INVALID_PAYLOAD, "Secuencia negativa.")
        if not math.isfinite(speed_kmh) or not 0 <= speed_kmh <= MAX_PLAUSIBLE_SPEED_KMH:
            raise TelemetryRejectedError(
                TelemetryRejectionReason.INVALID_PAYLOAD, f"Velocidad fuera de rango: {speed_kmh}"
            )
        if event_time.tzinfo is None or received_at.tzinfo is None:
            raise TelemetryRejectedError(
                TelemetryRejectionReason.INVALID_PAYLOAD, "Las marcas de tiempo deben incluir zona horaria."
            )
        return cls(
            id=uuid.uuid4(),
            message_id=message_id,
            device_id=device_id,
            trip_id=trip_id,
            sequence=sequence,
            event_time=event_time,
            received_at=received_at,
            position=position,
            speed_kmh=round(speed_kmh, 2),
            kind=kind,
            temporal_classification=temporal_classification,
        )

    @property
    def is_live(self) -> bool:
        return self.temporal_classification == TemporalClassification.LIVE

    @property
    def is_enriched(self) -> bool:
        return self.spatial_context is not None

    @property
    def transmission_lag_seconds(self) -> float:
        return (self.received_at - self.event_time).total_seconds()

    def enrich(self, context: SpatialContext, at: datetime) -> None:
        """Agrega el contexto espacial una sola vez; si la lectura llega de nuevo no hace nada."""
        if self.spatial_context is None:
            self.spatial_context = context
            self.enriched_at = at
