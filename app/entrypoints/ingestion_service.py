"""Proceso de ingesta.

Ingresan las lecturas del broker IoT (telemetry/raw/+) -> se parsean -> IngestTelemetryUseCase
(validación, deduplicación, clasificación LIVE/DELAYED, guardado) -> outbox ->
telemetry/normalized en el broker interno.

También le avisa a cada dispositivo qué viaje tiene activo, publicando un mensaje
retenido en devices/{code}/trip cuando llega trip/started o trip/ended.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from app.composition import monitoring_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.entrypoints.service_runtime import run_service, start_outbox_relay
from app.infrastructure.mqtt.message_parsers import (
    InvalidMessageError,
    parse_json_object,
    parse_raw_telemetry,
)
from app.infrastructure.mqtt.mqtt_endpoint import internal_endpoint, iot_endpoint
from app.infrastructure.mqtt.mqtt_event_publisher import MqttEventPublisher
from app.infrastructure.mqtt.mqtt_subscription import run_subscription
from app.modules.monitoring.application.use_cases.announce_trip_assignment import TripLifecycleNotice
from app.shared.application.integration_topics import (
    TELEMETRY_RAW_SUBSCRIPTION,
    TRIP_ENDED,
    TRIP_STARTED,
    device_code_from_raw_topic,
)

logger = logging.getLogger("cargo.ingestion")


class TelemetryIngestionHandler:
    def __init__(self, resources: AppResources) -> None:
        self._resources = resources

    async def __call__(self, topic: str, payload: bytes) -> None:
        received_at = datetime.now(UTC)  # received_at lo pone la plataforma, nunca el dispositivo
        device_code = device_code_from_raw_topic(topic)
        if device_code is None:
            logger.warning("telemetry on unexpected topic", extra={"topic": topic})
            return
        try:
            command = parse_raw_telemetry(device_code, payload, received_at)
        except InvalidMessageError as error:
            logger.warning("invalid telemetry message", extra={"topic": topic, "error": str(error)})
            return
        async with open_scope(self._resources) as scope:
            result = await monitoring_factory.ingest_telemetry(scope).execute(command)
        logger.info(
            "telemetry processed",
            extra={
                "device": command.device_code,
                "sequence": command.sequence,
                "outcome": result.outcome.value,
                "classification": result.temporal_classification,
                "reason": result.reason,
            },
        )


class TripAssignmentHandler:
    """Entrada MQTT: trip/started / trip/ended -> AnnounceTripAssignmentUseCase."""

    def __init__(self, resources: AppResources, iot_publisher: MqttEventPublisher) -> None:
        self._resources = resources
        self._iot_publisher = iot_publisher

    async def __call__(self, topic: str, payload: bytes) -> None:
        try:
            data = parse_json_object(payload)
            device_id = uuid.UUID(str(data["device_id"])) if data.get("device_id") else None
            notice = TripLifecycleNotice(
                trip_id=str(data["trip_id"]),
                trip_code=data.get("trip_code"),
                device_id=device_id,
                active=topic == TRIP_STARTED,
                details=data,
            )
        except (InvalidMessageError, KeyError, ValueError) as error:
            logger.warning("invalid trip control message", extra={"topic": topic, "error": str(error)})
            return
        async with open_scope(self._resources) as scope:
            await monitoring_factory.announce_trip_assignment(scope, self._iot_publisher).execute(notice)


async def main(resources: AppResources, stop: asyncio.Event) -> None:
    settings = resources.settings
    iot_publisher = MqttEventPublisher(iot_endpoint(settings), "cargo-ingestion-assignments")
    tasks = [
        start_outbox_relay(resources, "ingestion", stop),
        asyncio.create_task(
            run_subscription(
                iot_endpoint(settings),
                client_id="cargo-ingestion",
                topics=[TELEMETRY_RAW_SUBSCRIPTION],
                handler=TelemetryIngestionHandler(resources),
                stop=stop,
            )
        ),
        asyncio.create_task(
            run_subscription(
                internal_endpoint(settings),
                client_id="cargo-ingestion-trip-control",
                topics=[TRIP_STARTED, TRIP_ENDED],
                handler=TripAssignmentHandler(resources, iot_publisher),
                stop=stop,
            )
        ),
    ]
    await stop.wait()
    await asyncio.gather(*tasks, return_exceptions=True)
    await iot_publisher.close()


if __name__ == "__main__":
    run_service("ingestion", main)
