"""Tareas en segundo plano que corren dentro del proceso de la API."""

from __future__ import annotations

import asyncio
import logging

from app.composition import trips_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.core.realtime.connection_manager import ConnectionManager
from app.entrypoints.realtime_bridge import REALTIME_TOPICS, RealtimeBridge
from app.infrastructure.messaging.outbox_relay import OutboxRelay
from app.infrastructure.mqtt.mqtt_endpoint import internal_endpoint
from app.infrastructure.mqtt.mqtt_event_publisher import MqttEventPublisher
from app.infrastructure.mqtt.mqtt_subscription import SubscriptionState, run_subscription

logger = logging.getLogger("cargo.api.workers")


async def _reannounce_active_trips(resources: AppResources, stop: asyncio.Event) -> None:
    interval = resources.settings.trip_reannounce_interval_seconds
    while not stop.is_set():
        try:
            async with open_scope(resources) as scope:
                count = await trips_factory.reannounce_active_trips(scope).execute()
            logger.debug("active trips re-announced", extra={"count": count})
        except Exception:
            logger.exception("trip re-announcement failed")
        try:
            await asyncio.wait_for(stop.wait(), interval)
        except TimeoutError:
            continue


class ApiBackgroundWorkers:
    def __init__(self, resources: AppResources, connections: ConnectionManager) -> None:
        self._resources = resources
        self._connections = connections
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._publisher = MqttEventPublisher(internal_endpoint(resources.settings), "cargo-api-outbox")
        self.subscription_state = SubscriptionState()

    def start(self) -> None:
        relay = OutboxRelay(self._resources.session_factory, self._publisher, self._resources.outbox_signal)
        self._tasks = [
            asyncio.create_task(relay.run(self._stop), name="api-outbox-relay"),
            asyncio.create_task(
                run_subscription(
                    internal_endpoint(self._resources.settings),
                    client_id="cargo-api-realtime",
                    topics=REALTIME_TOPICS,
                    handler=RealtimeBridge(self._resources, self._connections),
                    stop=self._stop,
                    state=self.subscription_state,
                ),
                name="api-realtime-bridge",
            ),
            asyncio.create_task(_reannounce_active_trips(self._resources, self._stop), name="api-trip-reannounce"),
        ]

    async def stop(self) -> None:
        self._stop.set()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._publisher.close()
