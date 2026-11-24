"""ACK de aplicación de punta a punta: PostgreSQL/PostGIS real + Mosquitto real."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.entrypoints.ingestion_service import TelemetryIngestionHandler
from app.infrastructure.mqtt.mqtt_endpoint import MqttEndpoint
from app.infrastructure.mqtt.mqtt_event_publisher import MqttEventPublisher
from app.infrastructure.mqtt.mqtt_subscription import SubscriptionState, run_subscription
from app.modules.trips.infrastructure.persistence.postgres_trip_repository import PostgresTripRepository
from tests.support.seed import create_trip, seed_fleet, start_trip

pytestmark = pytest.mark.integration

HOST = os.environ.get("TEST_MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("TEST_MQTT_PORT", "51883"))


def _endpoint() -> MqttEndpoint:
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            pass
    except OSError:
        pytest.skip(f"Mosquitto not reachable at {HOST}:{PORT}")
    return MqttEndpoint(name="test", host=HOST, port=PORT, username=None, password=None)


def _reading(trip_id: uuid.UUID, device: str, sequence: int, message_id: str | None = None) -> dict[str, Any]:
    return {
        "message_id": message_id or str(uuid.uuid4()),
        "device_id": device,
        "trip_id": str(trip_id),
        "sequence": sequence,
        "event_time": datetime.now(UTC).isoformat(),
        "latitude": -12.05,
        "longitude": -77.04,
        "speed_kmh": 40.0,
        "emergency": False,
        "schema_version": 1,
    }


async def test_ingestion_acknowledges_after_saving(resources: AppResources) -> None:
    endpoint = _endpoint()
    fleet = await seed_fleet(resources, "301")
    code = await create_trip(resources, fleet)
    await start_trip(resources, code)
    async with open_scope(resources) as scope:
        trip = await PostgresTripRepository(scope.session).get_by_code(code)
    assert trip is not None

    device = fleet.device_code
    acks: list[dict[str, Any]] = []
    stop = asyncio.Event()
    state = SubscriptionState()

    async def collect(_topic: str, payload: bytes) -> None:
        acks.append(json.loads(payload))
        if len(acks) == 4:
            stop.set()

    listener = asyncio.create_task(
        run_subscription(
            endpoint,
            client_id=f"ack-{uuid.uuid4().hex[:8]}",
            topics=[f"devices/{device}/telemetry/ack"],
            handler=collect,
            stop=stop,
            state=state,
        )
    )
    for _ in range(50):
        if state.connected:
            break
        await asyncio.sleep(0.1)

    publisher = MqttEventPublisher(endpoint, f"ack-pub-{uuid.uuid4().hex[:8]}")
    handler = TelemetryIngestionHandler(resources, publisher)
    topic = f"telemetry/raw/{device}"
    first = _reading(trip.id, device, 0)
    try:
        await handler(topic, json.dumps(first).encode())  # nueva -> accepted
        await handler(topic, json.dumps(first).encode())  # reentrega -> duplicate
        await handler(topic, json.dumps(_reading(trip.id, device, 0)).encode())  # misma secuencia -> rejected
        await handler(topic, json.dumps({"message_id": "bad-1", "device_id": device}).encode())  # inválida
        await asyncio.wait_for(stop.wait(), timeout=10)
    finally:
        stop.set()
        await listener
        await publisher.close()

    assert [(a["status"], a.get("reason")) for a in acks] == [
        ("accepted", None),
        ("duplicate", "duplicate_message"),
        ("rejected", "sequence_conflict"),
        ("rejected", "invalid_payload"),
    ]
    assert acks[0]["message_id"] == acks[1]["message_id"] == first["message_id"]
