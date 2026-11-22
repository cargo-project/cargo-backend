"""Lotes de Siddhi en events/detected: cada evento de la lista se registra y se avisa."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text

from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.core.realtime.connection_manager import ConnectionManager
from app.entrypoints.realtime_bridge import RealtimeBridge
from app.modules.trips.infrastructure.persistence.postgres_trip_repository import PostgresTripRepository
from app.shared.application.integration_topics import EVENTS_DETECTED
from tests.support.seed import create_trip, seed_fleet, start_trip

pytestmark = pytest.mark.integration


class _RecordingConnections(ConnectionManager):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[dict[str, Any]] = []

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.sent.append(message)


async def _ongoing_trip_id(resources: AppResources, suffix: str) -> uuid.UUID:
    fleet = await seed_fleet(resources, suffix)
    code = await create_trip(resources, fleet)
    await start_trip(resources, code)
    async with open_scope(resources) as scope:
        trip = await PostgresTripRepository(scope.session).get_by_code(code)
    assert trip is not None
    return trip.id


def _connection_loss(trip_id: uuid.UUID) -> dict[str, Any]:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    return {
        "event": {
            "event_id": str(uuid.uuid4()),
            "event_type": "CONNECTION_LOSS",
            "trip_id": str(trip_id),
            "event_time_ms": now_ms - 1000,
            "detected_at_ms": now_ms,
            "started_at_ms": -1,
            "latitude": -12.05,
            "longitude": -77.04,
            "evidence_from_sequence": -1,
            "evidence_to_sequence": -1,
            "metric_value": 310.0,
            "delayed": False,
        }
    }


async def test_bridge_registers_every_event_of_a_siddhi_batch(resources: AppResources) -> None:
    trips = [await _ongoing_trip_id(resources, suffix) for suffix in ("101", "102")]
    batch = [_connection_loss(trips[0]), {"event": {"event_type": "CONNECTION_LOSS"}}, _connection_loss(trips[1])]
    connections = _RecordingConnections()

    await RealtimeBridge(resources, connections)(EVENTS_DETECTED, json.dumps(batch).encode())

    async with open_scope(resources) as scope:
        stored = (
            await scope.session.execute(
                text("SELECT trip_id FROM monitoring_events WHERE event_type = 'CONNECTION_LOSS'")
            )
        ).scalars()
        assert sorted(stored) == sorted(trips)  # los dos válidos, el elemento roto se descarta solo
    created = [m for m in connections.sent if m["type"] == "monitoring.event_created"]
    offline = [m for m in connections.sent if m["type"] == "device.connection_changed"]
    assert len(created) == 2 and len(offline) == 2
