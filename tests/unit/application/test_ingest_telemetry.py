"""Pipeline de ingesta: validación, deduplicación, LIVE/DELAYED y store-and-forward."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.modules.monitoring.application.dto.monitoring_dto import IngestionOutcome, RawTelemetryCommand
from app.modules.monitoring.application.services.telemetry_deduplicator import TelemetryDeduplicator
from app.modules.monitoring.application.use_cases.ingest_telemetry import IngestTelemetryUseCase
from app.modules.monitoring.domain.services.telemetry_acceptance_policy import (
    TelemetryAcceptancePolicy,
    TelemetryTripContext,
)
from app.modules.monitoring.domain.services.temporal_classifier import TemporalClassifier
from app.shared.application.integration_topics import TELEMETRY_NORMALIZED
from tests.unit.fakes import (
    T0,
    FakeClock,
    FakeUnitOfWork,
    InMemoryTelemetryRepository,
    RecordingConnections,
    RecordingPublisher,
    StaticTelemetryContextProvider,
)

DEVICE_ID = uuid.uuid4()
TRIP_ID = uuid.uuid4()
CONTEXT = TelemetryTripContext(
    device_id=DEVICE_ID,
    device_code="DEV-GW-001",
    device_active=True,
    trip_id=TRIP_ID,
    trip_code="TRP-1",
    vehicle_code="TRK-001",
    trip_status="ongoing",
    trip_device_id=DEVICE_ID,
    trip_started_at=T0,
    trip_ended_at=None,
)


class Pipeline:
    def __init__(self) -> None:
        self.telemetry = InMemoryTelemetryRepository()
        self.publisher = RecordingPublisher()
        self.uow = FakeUnitOfWork()
        self.connections = RecordingConnections()
        self.use_case = IngestTelemetryUseCase(
            telemetry=self.telemetry,
            contexts=StaticTelemetryContextProvider(CONTEXT),
            connections=self.connections,
            deduplicator=TelemetryDeduplicator(self.telemetry),
            policy=TelemetryAcceptancePolicy(max_future_skew=timedelta(seconds=120)),
            classifier=TemporalClassifier(timedelta(seconds=60)),
            publisher=self.publisher,
            uow=self.uow,
            clock=FakeClock(),
        )


@pytest.fixture
def pipeline() -> Pipeline:
    return Pipeline()


def raw(sequence: int, *, event_offset_s: float, received_offset_s: float, **overrides: object) -> RawTelemetryCommand:
    values: dict[str, object] = {
        "topic_device_code": "DEV-GW-001",
        "message_id": uuid.uuid4(),
        "device_code": "DEV-GW-001",
        "trip_id": TRIP_ID,
        "sequence": sequence,
        "event_time": T0 + timedelta(seconds=event_offset_s),
        "latitude": -12.05,
        "longitude": -77.04,
        "speed_kmh": 42.0,
        "emergency": False,
        "received_at": T0 + timedelta(seconds=received_offset_s),
    }
    values.update(overrides)
    return RawTelemetryCommand(**values)  # type: ignore[arg-type]


async def test_live_telemetry_is_persisted_and_published(pipeline: Pipeline) -> None:
    result = await pipeline.use_case.execute(raw(1, event_offset_s=10, received_offset_s=11))
    assert result.outcome == IngestionOutcome.ACCEPTED
    assert result.temporal_classification == "LIVE"
    stored = next(iter(pipeline.telemetry.items.values()))
    assert stored.event_time == T0 + timedelta(seconds=10)  # event_time nunca se pisa
    assert stored.received_at == T0 + timedelta(seconds=11)
    assert pipeline.publisher.topics() == [TELEMETRY_NORMALIZED]
    payload = pipeline.publisher.events[0].payload
    assert payload["temporal_classification"] == "LIVE"
    assert payload["trip_code"] == "TRP-1"
    assert pipeline.connections.calls == [(DEVICE_ID, T0 + timedelta(seconds=11))]


async def test_late_telemetry_is_delayed(pipeline: Pipeline) -> None:
    # generada 10:05, recibida 10:31
    result = await pipeline.use_case.execute(raw(1, event_offset_s=5 * 60, received_offset_s=31 * 60))
    assert result.temporal_classification == "DELAYED"


async def test_duplicate_message_id_is_ignored(pipeline: Pipeline) -> None:
    first = raw(1, event_offset_s=1, received_offset_s=2)
    await pipeline.use_case.execute(first)
    again = await pipeline.use_case.execute(first)  # reentrega QoS 1
    assert again.outcome == IngestionOutcome.DUPLICATE
    assert len(pipeline.telemetry.items) == 1
    assert pipeline.publisher.topics() == [TELEMETRY_NORMALIZED]


async def test_duplicate_sequence_with_other_message_id_is_rejected(pipeline: Pipeline) -> None:
    await pipeline.use_case.execute(raw(7, event_offset_s=1, received_offset_s=2))
    conflict = await pipeline.use_case.execute(raw(7, event_offset_s=3, received_offset_s=4))
    assert conflict.outcome == IngestionOutcome.REJECTED
    assert conflict.reason == "sequence_conflict"
    assert len(pipeline.telemetry.items) == 1


async def test_topic_and_payload_device_must_match(pipeline: Pipeline) -> None:
    result = await pipeline.use_case.execute(raw(1, event_offset_s=1, received_offset_s=1, topic_device_code="X-1"))
    assert result.outcome == IngestionOutcome.REJECTED
    assert result.reason == "topic_device_mismatch"


async def test_invalid_coordinates_are_rejected(pipeline: Pipeline) -> None:
    result = await pipeline.use_case.execute(raw(1, event_offset_s=1, received_offset_s=1, latitude=123.0))
    assert result.outcome == IngestionOutcome.REJECTED
    assert pipeline.uow.commits == 0


async def test_store_and_forward_burst_keeps_original_order_and_marks_history(pipeline: Pipeline) -> None:
    """El vehículo perdió conexión 20 minutos y guardó lecturas en SQLite.

    Al reconectar publica el atraso más los datos actuales, posiblemente duplicados.
    """
    backlog = [raw(seq, event_offset_s=seq * 30, received_offset_s=1500 + seq) for seq in range(1, 41)]
    current = raw(41, event_offset_s=1499, received_offset_s=1500)
    burst = [current, *backlog, backlog[3], backlog[10]]  # actual, luego el atraso y duplicados QoS 1
    outcomes = [await pipeline.use_case.execute(item) for item in burst]

    assert [o.outcome for o in outcomes].count(IngestionOutcome.ACCEPTED) == 41
    assert [o.outcome for o in outcomes].count(IngestionOutcome.DUPLICATE) == 2
    stored = sorted(pipeline.telemetry.items.values(), key=lambda t: t.event_time)
    assert [t.sequence for t in stored] == sorted(t.sequence for t in stored)  # mismo orden por event_time y sequence
    live = [t for t in stored if t.is_live]
    assert [t.sequence for t in live] == [41]  # solo la lectura nueva alimenta las reglas CEP operativas
    assert all(not t.is_live for t in stored if t.sequence <= 40)
