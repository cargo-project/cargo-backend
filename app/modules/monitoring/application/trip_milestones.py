"""Hitos del viaje que se vuelven eventos de monitoreo (alertas para el operador).

trip/started se publica al iniciar el viaje y se reanuncia cada cierto tiempo para
resincronizar CEP, por eso el id del evento se calcula a partir del viaje: el hito se
registra (y se notifica) una sola vez, llegue las veces que llegue.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.modules.monitoring.application.dto.monitoring_dto import DetectedEventCommand

_MILESTONE_NAMESPACE = uuid.UUID("6f1c2b8e-4d0a-4f4e-9a57-2c1d0b6e9f31")
TRIP_STARTED = "TRIP_STARTED"


def trip_started_event_id(trip_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_MILESTONE_NAMESPACE, f"{TRIP_STARTED}:{trip_id}")


def trip_started_command(
    *,
    trip_id: uuid.UUID,
    started_at: datetime,
    origin_latitude: float | None,
    origin_longitude: float | None,
    origin_label: str | None,
    destination_label: str | None,
) -> DetectedEventCommand:
    details: dict[str, str] = {}
    if origin_label:
        details["origin_label"] = origin_label
    if destination_label:
        details["destination_label"] = destination_label
    return DetectedEventCommand(
        event_id=trip_started_event_id(trip_id),
        event_type=TRIP_STARTED,
        trip_id=trip_id,
        event_time=started_at,
        detected_at=started_at,
        started_at=None,
        latitude=origin_latitude,
        longitude=origin_longitude,
        evidence_from_sequence=None,
        evidence_to_sequence=None,
        metric_value=None,
        extra_details=details,
    )
