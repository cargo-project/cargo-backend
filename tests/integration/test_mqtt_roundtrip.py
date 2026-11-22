"""Adaptadores MQTT contra un broker Mosquitto real (QoS 1, sesiones persistentes)."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid

import pytest

from app.infrastructure.mqtt.mqtt_endpoint import MqttEndpoint
from app.infrastructure.mqtt.mqtt_event_publisher import MqttEventPublisher
from app.infrastructure.mqtt.mqtt_subscription import SubscriptionState, run_subscription

pytestmark = pytest.mark.integration

HOST = os.environ.get("TEST_MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("TEST_MQTT_PORT", "51883"))


def _broker_available() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture
def endpoint() -> MqttEndpoint:
    if not _broker_available():
        pytest.skip(f"Mosquitto not reachable at {HOST}:{PORT}")
    return MqttEndpoint(
        name="test",
        host=HOST,
        port=PORT,
        username=os.environ.get("TEST_MQTT_USERNAME"),
        password=os.environ.get("TEST_MQTT_PASSWORD"),
    )


async def test_publish_subscribe_roundtrip_with_qos1(endpoint: MqttEndpoint) -> None:
    topic = f"test/{uuid.uuid4().hex}"
    received: list[bytes] = []
    stop = asyncio.Event()
    state = SubscriptionState()

    async def handler(_: str, payload: bytes) -> None:
        received.append(payload)
        if len(received) == 2:
            stop.set()

    task = asyncio.create_task(
        run_subscription(
            endpoint, client_id=f"sub-{uuid.uuid4().hex[:8]}", topics=[topic], handler=handler, stop=stop, state=state
        )
    )
    for _ in range(50):
        if state.connected:
            break
        await asyncio.sleep(0.1)
    publisher = MqttEventPublisher(endpoint, f"pub-{uuid.uuid4().hex[:8]}")
    await publisher.publish_json(topic, {"n": 1}, retain=False)
    await publisher.publish_json(topic, {"n": 2}, retain=False)
    await asyncio.wait_for(task, timeout=10)
    await publisher.close()
    assert received == [b'{"n":1}', b'{"n":2}']


async def test_handler_errors_do_not_stop_the_consumer(endpoint: MqttEndpoint) -> None:
    topic = f"test/{uuid.uuid4().hex}"
    seen: list[bytes] = []
    stop = asyncio.Event()
    state = SubscriptionState()

    async def handler(_: str, payload: bytes) -> None:
        seen.append(payload)
        if payload == b'{"bad":true}':
            raise ValueError("malformed")
        stop.set()

    task = asyncio.create_task(
        run_subscription(
            endpoint, client_id=f"sub-{uuid.uuid4().hex[:8]}", topics=[topic], handler=handler, stop=stop, state=state
        )
    )
    for _ in range(50):
        if state.connected:
            break
        await asyncio.sleep(0.1)
    publisher = MqttEventPublisher(endpoint, f"pub-{uuid.uuid4().hex[:8]}")
    await publisher.publish_json(topic, {"bad": True}, retain=False)
    await publisher.publish_json(topic, {"ok": True}, retain=False)
    await asyncio.wait_for(task, timeout=10)
    await publisher.close()
    assert len(seen) == 2
