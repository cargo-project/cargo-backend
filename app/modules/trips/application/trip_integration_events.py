"""Eventos de integración que publica el contexto de viajes (topics trip/*).

Los payloads son planos y las duraciones van en milisegundos porque Siddhi los
consume directo como atributos del stream (sin JSON anidado ni conversión de unidades en CEP).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.modules.trips.domain.entities.trip import Trip
from app.shared.application.event_publisher import IntegrationEvent
from app.shared.application.integration_topics import TRIP_CONFIG_UPDATED, TRIP_ENDED, TRIP_STARTED


def _epoch_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _monitoring_payload(trip: Trip) -> dict[str, Any]:
    config = trip.monitoring_configuration
    return {
        "deviation_min_events": int(config.route_deviation_min_events),
        "deviation_min_increase_m": float(config.route_deviation_min_increase_m),
        "deviation_window_ms": int(config.route_deviation_window_seconds) * 1000,
        "stop_speed_kmh": float(config.stop_speed_kmh),
        "stop_max_displacement_m": float(config.stop_max_displacement_m),
        "stop_duration_ms": int(config.stop_duration_seconds) * 1000,
        "connection_loss_ms": int(config.connection_loss_seconds) * 1000,
        "arrival_confirmation_ms": int(config.arrival_confirmation_seconds) * 1000,
    }


def trip_started_event(trip: Trip, *, occurred_at: datetime) -> IntegrationEvent:
    return IntegrationEvent(
        topic=TRIP_STARTED,
        payload={
            "trip_id": str(trip.id),
            "trip_code": trip.code,
            "device_id": str(trip.device_id) if trip.device_id else None,
            "occurred_at_ms": _epoch_ms(occurred_at),
            # Inicio real (los reanuncios lo mantienen); lo usa la alerta TRIP_STARTED.
            "started_at_ms": _epoch_ms(trip.started_at) if trip.started_at else None,
            "origin_label": trip.origin.label,
            "destination_label": trip.destination.label,
            # Esto le llega al dispositivo por su asignación retenida.
            "origin_latitude": trip.origin.point.latitude,
            "origin_longitude": trip.origin.point.longitude,
            "destination_latitude": trip.destination.point.latitude,
            "destination_longitude": trip.destination.point.longitude,
            **_monitoring_payload(trip),
        },
    )


def trip_config_updated_event(trip: Trip, *, occurred_at: datetime) -> IntegrationEvent:
    return IntegrationEvent(
        topic=TRIP_CONFIG_UPDATED,
        payload={
            "trip_id": str(trip.id),
            "trip_code": trip.code,
            "occurred_at_ms": _epoch_ms(occurred_at),
            **_monitoring_payload(trip),
        },
    )


def trip_ended_event(trip: Trip, *, occurred_at: datetime) -> IntegrationEvent:
    return IntegrationEvent(
        topic=TRIP_ENDED,
        payload={
            "trip_id": str(trip.id),
            "trip_code": trip.code,
            "device_id": str(trip.device_id) if trip.device_id else None,
            "status": trip.status.value,
            "reason": trip.end_reason,
            "occurred_at_ms": _epoch_ms(occurred_at),
        },
    )
