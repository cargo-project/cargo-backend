"""Publica JSON en un broker usando una conexión larga que se reconecta sola."""

from __future__ import annotations

import asyncio
import json
import logging

import aiomqtt

from app.infrastructure.mqtt.mqtt_endpoint import MqttEndpoint

logger = logging.getLogger("cargo.mqtt.publisher")


class MqttEventPublisher:
    def __init__(self, endpoint: MqttEndpoint, client_id: str) -> None:
        self._endpoint = endpoint
        self._client_id = client_id
        self._client: aiomqtt.Client | None = None
        self._lock = asyncio.Lock()

    async def publish_json(self, topic: str, payload: dict[str, object], *, retain: bool = False) -> None:
        body = json.dumps(payload, separators=(",", ":"), default=str).encode()
        async with self._lock:
            client = await self._connected_client()
            try:
                await client.publish(topic, payload=body, qos=1, retain=retain)
            except aiomqtt.MqttError:
                await self._discard_client()
                raise

    async def close(self) -> None:
        async with self._lock:
            await self._discard_client()

    async def _connected_client(self) -> aiomqtt.Client:
        if self._client is None:
            client = self._endpoint.create_client(self._client_id, clean_session=True)
            await client.__aenter__()
            self._client = client
            logger.info(
                "mqtt publisher connected",
                extra={"broker": self._endpoint.name, "client_id": self._client_id},
            )
        return self._client

    async def _discard_client(self) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            try:
                await client.__aexit__(None, None, None)
            except aiomqtt.MqttError:
                logger.debug("ignoring error while closing mqtt client")
