"""Proceso del servicio geoespacial.

Consume telemetry/normalized -> enriquece con PostGIS (EnrichTelemetryUseCase)
-> outbox -> telemetry/enriched. No genera alertas, no corre reglas CEP ni notifica.
"""

from __future__ import annotations

import asyncio
import logging

from app.composition import monitoring_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.entrypoints.service_runtime import run_service, start_outbox_relay
from app.infrastructure.mqtt.message_parsers import InvalidMessageError, parse_normalized_telemetry
from app.infrastructure.mqtt.mqtt_endpoint import internal_endpoint
from app.infrastructure.mqtt.mqtt_subscription import run_subscription
from app.shared.application.integration_topics import TELEMETRY_NORMALIZED

logger = logging.getLogger("cargo.geospatial")


class TelemetryEnrichmentHandler:
    def __init__(self, resources: AppResources) -> None:
        self._resources = resources

    async def __call__(self, topic: str, payload: bytes) -> None:
        try:
            message = parse_normalized_telemetry(payload)
        except InvalidMessageError as error:
            logger.warning("invalid normalized telemetry", extra={"error": str(error)})
            return
        async with open_scope(self._resources) as scope:
            enriched = await monitoring_factory.enrich_telemetry(scope).execute(message)
        logger.debug("telemetry enrichment", extra={"telemetry_id": str(message.telemetry_id), "enriched": enriched})


async def main(resources: AppResources, stop: asyncio.Event) -> None:
    tasks = [
        start_outbox_relay(resources, "geospatial", stop),
        asyncio.create_task(
            run_subscription(
                internal_endpoint(resources.settings),
                client_id="cargo-geospatial",
                topics=[TELEMETRY_NORMALIZED],
                handler=TelemetryEnrichmentHandler(resources),
                stop=stop,
            )
        ),
    ]
    await stop.wait()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    run_service("geospatial", main)
