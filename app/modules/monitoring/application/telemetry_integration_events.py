"""Payloads de telemetry/normalized y telemetry/enriched (JSON plano para Siddhi)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent
from app.modules.monitoring.domain.services.telemetry_acceptance_policy import TelemetryTripContext
from app.shared.application.event_publisher import IntegrationEvent
from app.shared.application.integration_topics import TELEMETRY_ENRICHED, TELEMETRY_NORMALIZED


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _epoch_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def telemetry_normalized_event(telemetry: TelemetryEvent, context: TelemetryTripContext) -> IntegrationEvent:
    return IntegrationEvent(
        topic=TELEMETRY_NORMALIZED,
        payload={
            "telemetry_id": str(telemetry.id),
            "message_id": str(telemetry.message_id),
            "device_id": str(telemetry.device_id),
            "device_code": context.device_code,
            "trip_id": str(telemetry.trip_id),
            "trip_code": context.trip_code,
            "vehicle_code": context.vehicle_code,
            "sequence": telemetry.sequence,
            "event_time": _iso(telemetry.event_time),
            "event_time_ms": _epoch_ms(telemetry.event_time),
            "received_at": _iso(telemetry.received_at),
            "latitude": telemetry.position.latitude,
            "longitude": telemetry.position.longitude,
            "speed_kmh": telemetry.speed_kmh,
            "kind": telemetry.kind.value,
            "temporal_classification": telemetry.temporal_classification.value,
        },
    )


def telemetry_enriched_event(telemetry: TelemetryEvent, normalized_payload: dict[str, Any]) -> IntegrationEvent:
    context = telemetry.spatial_context
    assert context is not None and telemetry.enriched_at is not None
    return IntegrationEvent(
        topic=TELEMETRY_ENRICHED,
        payload={
            **normalized_payload,
            "distance_to_destination_m": round(context.distance_to_destination_m, 2),
            "moving_away_m": round(context.moving_away_m, 2),
            "inside_destination": context.inside_destination,
            "displacement_window_m": round(context.displacement_window_m, 2),
            "zone_codes": list(context.zone_codes),
            "enriched_at": _iso(telemetry.enriched_at),
        },
    )
