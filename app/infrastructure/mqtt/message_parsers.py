"""Parseo estricto de los mensajes MQTT a comandos de aplicación.

Acá se valida el esquema (tipos, campos obligatorios, tamaño): los bytes mal formados
nunca llegan a los casos de uso. Las reglas de negocio se validan después en el
dominio (TelemetryAcceptancePolicy, TelemetryEvent.receive).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from app.modules.monitoring.application.dto.monitoring_dto import (
    DetectedEventCommand,
    NormalizedTelemetry,
    RawTelemetryCommand,
)
from app.modules.monitoring.application.trip_milestones import trip_started_command

MAX_PAYLOAD_BYTES = 4096
# Tope de eventos por lote de Siddhi (cada uno sigue limitado a MAX_PAYLOAD_BYTES en promedio).
MAX_BATCH_EVENTS = 500


class InvalidMessageError(ValueError):
    """El payload no es JSON válido o no cumple el esquema esperado."""


class _RawTelemetryMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    message_id: uuid.UUID
    device_id: str = Field(min_length=2, max_length=24)
    trip_id: uuid.UUID
    sequence: int = Field(ge=0, le=2**62)
    event_time: AwareDatetime
    latitude: float
    longitude: float
    speed_kmh: float = Field(ge=0)
    emergency: bool = False
    schema_version: int = 1


class _DetectedEventMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    event_id: uuid.UUID
    event_type: str = Field(max_length=40)
    trip_id: uuid.UUID
    event_time_ms: int
    detected_at_ms: int
    started_at_ms: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    evidence_from_sequence: int | None = None
    evidence_to_sequence: int | None = None
    metric_value: float | None = None
    delayed: bool = False


def _decode(payload: bytes, limit: int) -> Any:
    if len(payload) > limit:
        raise InvalidMessageError(f"payload too large ({len(payload)} bytes)")
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidMessageError("payload is not valid JSON") from error


def _unwrap(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise InvalidMessageError("payload must be a JSON object")
    # El mapper JSON de Siddhi envuelve los atributos en {"event": {...}}.
    inner = data.get("event")
    return inner if isinstance(inner, dict) else data


def _load_json(payload: bytes) -> dict[str, Any]:
    return _unwrap(_decode(payload, MAX_PAYLOAD_BYTES))


def _from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, UTC)


def parse_raw_telemetry(topic_device_code: str, payload: bytes, received_at: datetime) -> RawTelemetryCommand:
    try:
        message = _RawTelemetryMessage.model_validate(_load_json(payload))
    except ValidationError as error:
        raise InvalidMessageError(error.errors(include_url=False)[0]["msg"]) from error
    return RawTelemetryCommand(
        topic_device_code=topic_device_code.upper(),
        message_id=message.message_id,
        device_code=message.device_id.upper(),
        trip_id=message.trip_id,
        sequence=message.sequence,
        event_time=message.event_time.astimezone(UTC),
        latitude=message.latitude,
        longitude=message.longitude,
        speed_kmh=message.speed_kmh,
        emergency=message.emergency,
        received_at=received_at,
    )


def parse_normalized_telemetry(payload: bytes) -> NormalizedTelemetry:
    data = _load_json(payload)
    try:
        return NormalizedTelemetry(
            telemetry_id=uuid.UUID(str(data["telemetry_id"])),
            trip_id=uuid.UUID(str(data["trip_id"])),
            payload=data,
        )
    except (KeyError, ValueError) as error:
        raise InvalidMessageError("normalized telemetry without telemetry_id/trip_id") from error


@dataclass(frozen=True, slots=True)
class DetectedEventBatch:
    """Eventos de un mensaje de events/detected; los elementos inválidos van aparte."""

    commands: list[DetectedEventCommand]
    rejected: list[str]


def parse_detected_events(payload: bytes) -> DetectedEventBatch:
    """events/detected -> uno o varios eventos.

    Siddhi publica {"event": {...}} cuando sale un solo evento, pero si en el mismo
    ciclo salen varios (p. ej. el trigger de 5 s detecta varias pérdidas de conexión a
    la vez) manda una lista [{"event": {...}}, ...]. Cada elemento se valida por su
    cuenta: uno malo no tumba al resto del lote.
    """
    data = _decode(payload, MAX_PAYLOAD_BYTES * MAX_BATCH_EVENTS)
    if not isinstance(data, list):
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise InvalidMessageError(f"payload too large ({len(payload)} bytes)")
        return DetectedEventBatch([_detected_event_command(_unwrap(data))], [])
    if len(data) > MAX_BATCH_EVENTS:
        raise InvalidMessageError(f"batch too large ({len(data)} events)")
    commands: list[DetectedEventCommand] = []
    rejected: list[str] = []
    for index, item in enumerate(data):
        try:
            commands.append(_detected_event_command(_unwrap(item)))
        except InvalidMessageError as error:
            rejected.append(f"item {index}: {error}")
    return DetectedEventBatch(commands, rejected)


def parse_detected_event(payload: bytes) -> DetectedEventCommand:
    return _detected_event_command(_load_json(payload))


def _detected_event_command(data: dict[str, Any]) -> DetectedEventCommand:
    try:
        message = _DetectedEventMessage.model_validate(data)
    except ValidationError as error:
        raise InvalidMessageError(error.errors(include_url=False)[0]["msg"]) from error
    started = message.started_at_ms
    return DetectedEventCommand(
        event_id=message.event_id,
        event_type=message.event_type,
        trip_id=message.trip_id,
        event_time=_from_ms(message.event_time_ms),
        detected_at=_from_ms(message.detected_at_ms),
        started_at=_from_ms(started) if started and started > 0 else None,
        latitude=message.latitude,
        longitude=message.longitude,
        evidence_from_sequence=(
            message.evidence_from_sequence
            if message.evidence_from_sequence is not None and message.evidence_from_sequence >= 0
            else None
        ),
        evidence_to_sequence=(
            message.evidence_to_sequence
            if message.evidence_to_sequence is not None and message.evidence_to_sequence >= 0
            else None
        ),
        metric_value=message.metric_value,
        delayed=message.delayed,
    )


class _TripStartedMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    trip_id: uuid.UUID
    occurred_at_ms: int
    started_at_ms: int | None = None
    origin_latitude: float | None = None
    origin_longitude: float | None = None
    origin_label: str | None = Field(default=None, max_length=300)
    destination_label: str | None = Field(default=None, max_length=300)


def parse_trip_started(payload: bytes) -> DetectedEventCommand:
    """trip/started -> alerta TRIP_STARTED (con id idempotente, ver trip_milestones)."""
    try:
        message = _TripStartedMessage.model_validate(_load_json(payload))
    except ValidationError as error:
        raise InvalidMessageError(error.errors(include_url=False)[0]["msg"]) from error
    return trip_started_command(
        trip_id=message.trip_id,
        started_at=_from_ms(message.started_at_ms or message.occurred_at_ms),
        origin_latitude=message.origin_latitude,
        origin_longitude=message.origin_longitude,
        origin_label=message.origin_label,
        destination_label=message.destination_label,
    )


def parse_json_object(payload: bytes) -> dict[str, Any]:
    return _load_json(payload)
