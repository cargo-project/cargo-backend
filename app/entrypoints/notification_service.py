"""Proceso de notificaciones.

Escucha events/detected (CEP) y trip/started (alerta de viaje iniciado) -> registra el
MonitoringEvent (idempotente, así queda guardado aunque la API esté caída) ->
DispatchEventNotificationsUseCase -> Telegram. Cuando trip/started se reanuncia se
reutiliza el mismo evento y no se vuelve a notificar (una notificación por evento y destinatario).
"""

from __future__ import annotations

import asyncio
import logging

from app.composition import monitoring_factory, notifications_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.entrypoints.service_runtime import run_service
from app.infrastructure.mqtt.message_parsers import (
    InvalidMessageError,
    parse_detected_events,
    parse_trip_started,
)
from app.infrastructure.mqtt.mqtt_endpoint import internal_endpoint
from app.infrastructure.mqtt.mqtt_subscription import run_subscription
from app.modules.monitoring.application.dto.monitoring_dto import DetectedEventCommand
from app.modules.notifications.application.dto.notification_dto import EventNotificationRequest
from app.shared.application.integration_topics import EVENTS_DETECTED, TRIP_STARTED
from app.shared.domain.errors import DomainError

logger = logging.getLogger("cargo.notifications")


class DetectedEventNotificationHandler:
    def __init__(self, resources: AppResources) -> None:
        self._resources = resources

    async def __call__(self, topic: str, payload: bytes) -> None:
        try:
            if topic == TRIP_STARTED:
                commands = [parse_trip_started(payload)]
            else:
                batch = parse_detected_events(payload)
                commands = batch.commands
                for reason in batch.rejected:
                    logger.warning("invalid detected event", extra={"error": reason})
        except InvalidMessageError as error:
            logger.warning("invalid detected event", extra={"error": str(error)})
            return
        # Siddhi puede mandar varios eventos en un solo mensaje: cada uno se procesa aparte
        # para que una falla puntual no deje sin notificar al resto del lote.
        for command in commands:
            try:
                await self._handle(command)
            except Exception:
                logger.exception("detected event handling failed", extra={"event_id": str(command.event_id)})

    async def _handle(self, command: DetectedEventCommand) -> None:
        try:
            async with open_scope(self._resources) as scope:
                registered = await monitoring_factory.register_detected_event(scope).execute(command)
        except DomainError as error:
            logger.warning("detected event rejected", extra={"event_id": str(command.event_id), "error": error.message})
            return
        request = EventNotificationRequest(
            monitoring_event_id=registered.event_id,
            trip_id=registered.trip.trip_id,
            trip_code=registered.trip.trip_code,
            vehicle_code=registered.trip.vehicle_code,
            driver_name=registered.trip.driver_name,
            event_type=registered.event_type,
            severity=registered.severity,
            description=registered.description,
            detected_at=registered.detected_at,
            latitude=registered.latitude,
            longitude=registered.longitude,
            delayed=registered.delayed,
            occurred_at=registered.occurred_at,
        )
        async with open_scope(self._resources) as scope:
            summary = await notifications_factory.dispatch_event_notifications(scope).execute(request)
        logger.info(
            "notifications dispatched",
            extra={
                "event_id": str(registered.event_id),
                "type": registered.event_type,
                "sent": summary.sent,
                "failed": summary.failed,
                "skipped": summary.skipped,
            },
        )


async def main(resources: AppResources, stop: asyncio.Event) -> None:
    task = asyncio.create_task(
        run_subscription(
            internal_endpoint(resources.settings),
            client_id="cargo-notifications",
            topics=[EVENTS_DETECTED, TRIP_STARTED],
            handler=DetectedEventNotificationHandler(resources),
            stop=stop,
        )
    )
    await stop.wait()
    await asyncio.gather(task, return_exceptions=True)


if __name__ == "__main__":
    run_service("notifications", main)
