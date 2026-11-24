"""ACK de aplicación de la ingesta: se confirma solo lo que quedó guardado o lo que nunca se va a aceptar."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from app.entrypoints import ingestion_service
from app.entrypoints.ingestion_service import TelemetryIngestionHandler
from app.modules.monitoring.application.dto.monitoring_dto import IngestionOutcome, IngestionResult

TOPIC = "telemetry/raw/DEV-GW-001"
ACK_TOPIC = "devices/DEV-GW-001/telemetry/ack"


class FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[tuple[str, dict[str, object]]] = []
        self._fail = fail

    async def publish_json(self, topic: str, payload: dict[str, object], *, retain: bool = False) -> None:
        if self._fail:
            raise RuntimeError("broker down")
        self.sent.append((topic, payload))


def _reading(message_id: str) -> bytes:
    return json.dumps(
        {
            "message_id": message_id,
            "device_id": "DEV-GW-001",
            "trip_id": str(uuid.uuid4()),
            "sequence": 0,
            "event_time": datetime.now(UTC).isoformat(),
            "latitude": -12.05,
            "longitude": -77.04,
            "speed_kmh": 30.0,
        }
    ).encode()


@pytest.fixture
def use_case(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Reemplaza el caso de uso de ingesta; 'outcome' es un IngestionResult o una excepción a lanzar."""
    state: dict[str, Any] = {"outcome": IngestionResult(IngestionOutcome.ACCEPTED, temporal_classification="LIVE")}

    class _UseCase:
        async def execute(self, _command: object) -> IngestionResult:
            outcome = state["outcome"]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome  # type: ignore[no-any-return]

    @asynccontextmanager
    async def _scope(_resources: object) -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(ingestion_service, "open_scope", _scope)
    monkeypatch.setattr(ingestion_service.monitoring_factory, "ingest_telemetry", lambda _scope: _UseCase())
    return state


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (IngestionResult(IngestionOutcome.ACCEPTED), {"status": "accepted"}),
        (IngestionResult(IngestionOutcome.DUPLICATE, reason="duplicate_message"), {"status": "duplicate"}),
        (IngestionResult(IngestionOutcome.REJECTED, reason="unknown_trip"), {"status": "rejected"}),
    ],
)
async def test_ack_after_saving_with_outcome(
    use_case: dict[str, Any], result: IngestionResult, expected: dict[str, str]
) -> None:
    use_case["outcome"] = result
    publisher = FakePublisher()
    message_id = str(uuid.uuid4())

    await TelemetryIngestionHandler(object(), publisher)(TOPIC, _reading(message_id))  # type: ignore[arg-type]

    assert len(publisher.sent) == 1
    topic, ack = publisher.sent[0]
    assert topic == ACK_TOPIC
    assert ack["message_id"] == message_id
    assert ack["status"] == expected["status"]
    assert ack.get("reason") == result.reason


async def test_no_ack_when_saving_fails(use_case: dict[str, Any]) -> None:
    """Base de datos caída: sin ACK, el dispositivo conserva la lectura y la reenvía."""
    use_case["outcome"] = ConnectionError("database unavailable")
    publisher = FakePublisher()

    with pytest.raises(ConnectionError):
        await TelemetryIngestionHandler(object(), publisher)(TOPIC, _reading(str(uuid.uuid4())))  # type: ignore[arg-type]

    assert publisher.sent == []


async def test_invalid_payload_with_message_id_is_rejected(use_case: dict[str, Any]) -> None:
    publisher = FakePublisher()
    payload = json.dumps({"message_id": "abc-123", "device_id": "DEV-GW-001"}).encode()

    await TelemetryIngestionHandler(object(), publisher)(TOPIC, payload)  # type: ignore[arg-type]

    assert publisher.sent == [(ACK_TOPIC, {"message_id": "abc-123", "status": "rejected", "reason": "invalid_payload"})]


async def test_unparseable_payload_gets_no_ack(use_case: dict[str, Any]) -> None:
    publisher = FakePublisher()

    await TelemetryIngestionHandler(object(), publisher)(TOPIC, b"not json")  # type: ignore[arg-type]

    assert publisher.sent == []


async def test_ack_publish_failure_does_not_break_ingestion(use_case: dict[str, Any]) -> None:
    """Si el ACK no sale, la lectura ya quedó guardada: el reenvío del dispositivo recibirá 'duplicate'."""
    await TelemetryIngestionHandler(object(), FakePublisher(fail=True))(TOPIC, _reading(str(uuid.uuid4())))  # type: ignore[arg-type]
