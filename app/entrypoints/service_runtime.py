"""Arranque común de los procesos del pipeline (ingesta, geoespacial, notificaciones)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable, Callable

from app.composition.resources import AppResources
from app.core.config.settings import Settings, get_settings
from app.core.logging.logging_config import configure_logging
from app.infrastructure.messaging.outbox_relay import OutboxRelay
from app.infrastructure.mqtt.mqtt_endpoint import internal_endpoint
from app.infrastructure.mqtt.mqtt_event_publisher import MqttEventPublisher

ServiceMain = Callable[[AppResources, asyncio.Event], Awaitable[None]]


def start_outbox_relay(resources: AppResources, service_name: str, stop: asyncio.Event) -> asyncio.Task[None]:
    publisher = MqttEventPublisher(internal_endpoint(resources.settings), f"cargo-{service_name}-outbox")
    relay = OutboxRelay(resources.session_factory, publisher, resources.outbox_signal)
    return asyncio.create_task(relay.run(stop), name=f"{service_name}-outbox-relay")


async def _run(service_name: str, main: ServiceMain, settings: Settings) -> None:
    logger = logging.getLogger(f"cargo.{service_name}")
    resources = AppResources.build(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # consolas de Windows en desarrollo
            loop.add_signal_handler(sig, stop.set)
    logger.info("service starting", extra={"service": service_name, "environment": settings.environment})
    try:
        await main(resources, stop)
    finally:
        await resources.aclose()
        logger.info("service stopped", extra={"service": service_name})


def run_service(service_name: str, main: ServiceMain) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    asyncio.run(_run(service_name, main, settings))
