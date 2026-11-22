"""Adaptador de entrada que corre dentro de la API.

Se suscribe al broker interno y convierte los eventos del pipeline en avisos por
WebSocket; además cierra el viaje cuando CEP confirma DESTINATION_ARRIVAL.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.composition import monitoring_factory, trips_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.core.realtime.connection_manager import ConnectionManager
from app.infrastructure.mqtt.message_parsers import (
    InvalidMessageError,
    parse_detected_events,
    parse_json_object,
    parse_trip_started,
)
from app.modules.monitoring.application.dto.monitoring_dto import DetectedEventCommand
from app.shared.application.integration_topics import (
    EVENTS_DETECTED,
    TELEMETRY_ENRICHED,
    TRIP_CONFIG_UPDATED,
    TRIP_ENDED,
    TRIP_STARTED,
)
from app.shared.domain.errors import DomainError

logger = logging.getLogger("cargo.realtime")

REALTIME_TOPICS = [TELEMETRY_ENRICHED, EVENTS_DETECTED, TRIP_STARTED, TRIP_ENDED, TRIP_CONFIG_UPDATED]
_FRESH_ALERT_WINDOW = timedelta(minutes=2)


class RealtimeBridge:
    def __init__(self, resources: AppResources, connections: ConnectionManager) -> None:
        self._resources = resources
        self._connections = connections

    async def __call__(self, topic: str, payload: bytes) -> None:
        try:
            if topic == TELEMETRY_ENRICHED:
                await self._on_position(payload)
            elif topic == EVENTS_DETECTED:
                await self._on_detected_events(payload)
            elif topic in (TRIP_STARTED, TRIP_ENDED, TRIP_CONFIG_UPDATED):
                await self._on_trip_change(topic, payload)
        except InvalidMessageError as error:
            logger.warning("invalid realtime message", extra={"topic": topic, "error": str(error)})

    async def _on_position(self, payload: bytes) -> None:
        data = parse_json_object(payload)
        await self._connections.broadcast(
            {
                "type": "position.updated",
                "tripId": data.get("trip_code"),
                "vehicleId": data.get("vehicle_code"),
                "classification": data.get("temporal_classification"),
            }
        )

    async def _on_detected_events(self, payload: bytes) -> None:
        # Siddhi manda una lista cuando emite varios eventos en el mismo ciclo; cada uno
        # se registra y se avisa por separado (una falla puntual no frena al resto).
        batch = parse_detected_events(payload)
        for reason in batch.rejected:
            logger.warning("invalid realtime message", extra={"topic": EVENTS_DETECTED, "error": reason})
        for command in batch.commands:
            try:
                await self._on_detected_event(command)
            except Exception:
                logger.exception("detected event handling failed", extra={"event_id": str(command.event_id)})

    async def _on_detected_event(self, command: DetectedEventCommand) -> None:
        try:
            async with open_scope(self._resources) as scope:
                registered = await monitoring_factory.register_detected_event(scope).execute(command)
        except DomainError as error:
            logger.warning("detected event rejected", extra={"event_id": str(command.event_id), "error": error.message})
            return
        # Solo una llegada confirmada en vivo cierra el viaje.
        if registered.event_type == "DESTINATION_ARRIVAL" and not registered.delayed:
            async with open_scope(self._resources) as scope:
                finished = await trips_factory.finish_trip(scope).finish_on_arrival(registered.trip.trip_id)
            if finished:
                logger.info("trip completed on destination arrival", extra={"trip": registered.trip.trip_code})
        message = {
            "type": "monitoring.event_created",
            "tripId": registered.trip.trip_code,
            "vehicleId": registered.trip.vehicle_code,
            "eventId": str(registered.event_id),
            "eventType": registered.event_type,
            "delayed": registered.delayed,
        }
        await self._connections.broadcast(message)
        if registered.event_type == "CONNECTION_LOSS":
            await self._connections.broadcast({**message, "type": "device.connection_changed", "online": False})

    async def _on_trip_started_alert(self, payload: bytes) -> None:
        """Registra la alerta TRIP_STARTED (idempotente; el servicio de notificaciones también la registra)."""
        command = parse_trip_started(payload)
        try:
            async with open_scope(self._resources) as scope:
                registered = await monitoring_factory.register_detected_event(scope).execute(command)
        except DomainError as error:
            logger.warning("trip started alert rejected", extra={"trip": str(command.trip_id), "error": error.message})
            return
        # trip/started se reanuncia cada minuto: solo empujamos la alerta mientras es nueva.
        if registered.created or datetime.now(UTC) - registered.detected_at < _FRESH_ALERT_WINDOW:
            await self._connections.broadcast(
                {
                    "type": "monitoring.event_created",
                    "tripId": registered.trip.trip_code,
                    "vehicleId": registered.trip.vehicle_code,
                    "eventId": str(registered.event_id),
                    "eventType": registered.event_type,
                }
            )

    async def _on_trip_change(self, topic: str, payload: bytes) -> None:
        if topic == TRIP_STARTED:
            await self._on_trip_started_alert(payload)
        data = parse_json_object(payload)
        status = {TRIP_STARTED: "ongoing", TRIP_CONFIG_UPDATED: "ongoing"}.get(topic, data.get("status"))
        await self._connections.broadcast(
            {
                "type": "trip.status_changed" if topic != TRIP_CONFIG_UPDATED else "trip.config_updated",
                "tripId": data.get("trip_code"),
                "status": status,
            }
        )
