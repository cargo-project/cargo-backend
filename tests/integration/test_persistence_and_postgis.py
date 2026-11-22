"""Adaptadores PostgreSQL/PostGIS contra una base real migrada con Alembic."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.composition import monitoring_factory, trips_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.infrastructure.messaging.outbox_model import IntegrationOutboxModel
from app.infrastructure.messaging.outbox_relay import OutboxRelay
from app.infrastructure.messaging.outbox_signal import OutboxSignal
from app.modules.monitoring.application.dto.monitoring_dto import (
    IngestionOutcome,
    NormalizedTelemetry,
    RawTelemetryCommand,
)
from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent, TelemetryKind
from app.modules.monitoring.domain.repositories.monitoring_repositories import DuplicateTelemetryError
from app.modules.monitoring.domain.value_objects.temporal_classification import TemporalClassification
from app.modules.monitoring.infrastructure.geospatial.postgis_spatial_context_analyzer import (
    PostgisSpatialContextAnalyzer,
)
from app.modules.monitoring.infrastructure.persistence.postgres_monitoring_repositories import (
    PostgresTelemetryRepository,
)
from app.modules.trips.domain.value_objects.trip_status import TripStatus
from app.modules.trips.infrastructure.persistence.postgres_trip_repository import PostgresTripRepository
from app.shared.application.integration_topics import TELEMETRY_ENRICHED, TELEMETRY_NORMALIZED, TRIP_STARTED
from app.shared.domain.geo_point import GeoPoint
from tests.support.seed import ICA, LIMA, create_trip, seed_fleet, start_trip

pytestmark = pytest.mark.integration


async def _ongoing_trip(resources: AppResources) -> tuple[str, uuid.UUID, str]:
    fleet = await seed_fleet(resources)
    code = await create_trip(resources, fleet)
    await start_trip(resources, code)
    async with open_scope(resources) as scope:
        trip = await PostgresTripRepository(scope.session).get_by_code(code)
    assert trip is not None
    return code, trip.id, fleet.device_code


async def test_trip_aggregate_roundtrip_and_destination_geofence(resources: AppResources) -> None:
    _code, trip_id, _ = await _ongoing_trip(resources)
    async with open_scope(resources) as scope:
        trip = await PostgresTripRepository(scope.session).get_by_id(trip_id)
        assert trip is not None
        assert trip.status == TripStatus.ONGOING
        assert trip.origin.point == GeoPoint(*LIMA)
        assert len(trip.recipient_ids) == 1
        assert await scope.session.scalar(text("SELECT to_regclass('planned_routes')")) is None  # no hay rutas
        radius = await scope.session.scalar(
            text(
                "SELECT round(ST_Distance(ST_Centroid(area)::geography,"
                " ST_PointN(ST_ExteriorRing(area), 1)::geography)::numeric) "
                "FROM geofences WHERE trip_id = :t AND kind = 'destination'"
            ),
            {"t": trip_id},
        )
        assert 140 <= float(radius) <= 160  # radio de llegada por defecto: 150 m
        outbox = await scope.session.scalars(select(IntegrationOutboxModel.topic))
        assert TRIP_STARTED in list(outbox)


async def test_concurrent_start_is_prevented_by_partial_unique_index(resources: AppResources) -> None:
    _code, trip_id, _ = await _ongoing_trip(resources)
    async with open_scope(resources) as scope:
        vehicle_id = await scope.session.scalar(text("SELECT vehicle_id FROM trips WHERE id = :t"), {"t": trip_id})
        with pytest.raises(Exception, match=r"uq_trips_ongoing_(vehicle|driver)"):
            await scope.session.execute(
                text(
                    "INSERT INTO trips (id, code, vehicle_id, driver_id, origin_label, origin, destination_label,"
                    " destination, cargo_description, status, monitoring_configuration, created_at, version)"
                    " SELECT gen_random_uuid(), 'DUP', vehicle_id, driver_id, origin_label, origin, destination_label,"
                    " destination, cargo_description, 'ongoing', monitoring_configuration, now(), 1 FROM trips"
                    " WHERE id = :t"
                ),
                {"t": trip_id},
            )
        assert vehicle_id is not None


def _raw(
    trip_id: uuid.UUID,
    device: str,
    sequence: int,
    lat: float,
    lon: float,
    *,
    event_time: datetime,
    received_at: datetime,
    message_id: uuid.UUID | None = None,
) -> RawTelemetryCommand:
    return RawTelemetryCommand(
        topic_device_code=device,
        message_id=message_id or uuid.uuid4(),
        device_code=device,
        trip_id=trip_id,
        sequence=sequence,
        event_time=event_time,
        latitude=lat,
        longitude=lon,
        speed_kmh=55.0,
        emergency=False,
        received_at=received_at,
    )


async def test_ingestion_and_enrichment_with_postgis(resources: AppResources) -> None:
    _, trip_id, device = await _ongoing_trip(resources)
    now = datetime.now(UTC)
    halfway = (LIMA[0] + (ICA[0] - LIMA[0]) * 0.5, LIMA[1] + (ICA[1] - LIMA[1]) * 0.5)
    turned_back = (LIMA[0] + (ICA[0] - LIMA[0]) * 0.25, LIMA[1] + (ICA[1] - LIMA[1]) * 0.25)  # volvió hacia atrás
    at_destination = ICA

    results = []
    for seq, point in enumerate([halfway, turned_back, at_destination], start=1):
        moment = now + timedelta(seconds=seq)
        async with open_scope(resources) as scope:
            results.append(
                await monitoring_factory.ingest_telemetry(scope).execute(
                    _raw(trip_id, device, seq, *point, event_time=moment, received_at=moment)
                )
            )
    assert all(r.outcome == IngestionOutcome.ACCEPTED for r in results)
    assert all(r.temporal_classification == "LIVE" for r in results)

    contexts = []
    for result in results:
        assert result.telemetry_id is not None
        async with open_scope(resources) as scope:
            enriched = await monitoring_factory.enrich_telemetry(scope).execute(
                NormalizedTelemetry(
                    telemetry_id=result.telemetry_id, trip_id=trip_id, payload={"trip_id": str(trip_id)}
                )
            )
            assert enriched
            telemetry = await PostgresTelemetryRepository(scope.session).get(result.telemetry_id)
            assert telemetry is not None and telemetry.spatial_context is not None
            contexts.append(telemetry.spatial_context)

    # No hay ruta: todo es respecto al destino.
    assert contexts[0].moving_away_m == 0.0  # primera lectura: no hay con qué comparar
    gap = contexts[1].distance_to_destination_m - contexts[0].distance_to_destination_m
    assert gap > 50_000  # volvió hacia Lima (~75 km más lejos de Ica)
    assert abs(contexts[1].moving_away_m - gap) < 1  # alejamiento = lo que se pasó del punto más cercano
    assert contexts[2].moving_away_m == 0.0 and contexts[2].inside_destination is True
    assert contexts[0].inside_destination is False

    async with open_scope(resources) as scope:
        trip_code = await scope.session.scalar(text("SELECT code FROM trips WHERE id = :t"), {"t": trip_id})
        view = await trips_factory.get_trip(scope).execute(trip_code)
    assert view.progress == 99  # en el destino; recién es 100 cuando CEP confirma la llegada

    async with open_scope(resources) as scope:
        topics = list(await scope.session.scalars(select(IntegrationOutboxModel.topic)))
        assert topics.count(TELEMETRY_NORMALIZED) == 3
        assert topics.count(TELEMETRY_ENRICHED) == 3
        last_connection = await scope.session.scalar(text("SELECT last_connection_at FROM iot_devices"))
        assert last_connection is not None


async def test_database_enforces_telemetry_idempotency(resources: AppResources) -> None:
    _, trip_id, _ = await _ongoing_trip(resources)
    async with open_scope(resources) as scope:
        device_id = await scope.session.scalar(text("SELECT device_id FROM trips WHERE id = :t"), {"t": trip_id})
    now = datetime.now(UTC)

    def telemetry(sequence: int, message_id: uuid.UUID) -> TelemetryEvent:
        return TelemetryEvent.receive(
            message_id=message_id,
            device_id=device_id,
            trip_id=trip_id,
            sequence=sequence,
            event_time=now,
            received_at=now,
            position=GeoPoint(*LIMA),
            speed_kmh=1,
            kind=TelemetryKind.POSITION,
            temporal_classification=TemporalClassification.LIVE,
        )

    message_id = uuid.uuid4()
    async with open_scope(resources) as scope:
        await PostgresTelemetryRepository(scope.session).add(telemetry(1, message_id))
        await scope.uow.commit()
    for duplicate in (telemetry(2, message_id), telemetry(1, uuid.uuid4())):  # mismo message_id / misma secuencia
        async with open_scope(resources) as scope:
            with pytest.raises(DuplicateTelemetryError):
                await PostgresTelemetryRepository(scope.session).add(duplicate)


async def test_displacement_window_supports_stop_detection(resources: AppResources) -> None:
    _, trip_id, device = await _ongoing_trip(resources)
    start = datetime.now(UTC) - timedelta(seconds=30)
    ids = []
    for seq, offset in enumerate([0.0, 0.00005, 0.0001], start=1):  # avanza ~11 m en total
        async with open_scope(resources) as scope:
            result = await monitoring_factory.ingest_telemetry(scope).execute(
                _raw(
                    trip_id,
                    device,
                    seq,
                    LIMA[0] + offset,
                    LIMA[1],
                    event_time=start + timedelta(seconds=seq * 5),
                    received_at=start + timedelta(seconds=seq * 5 + 1),
                )
            )
            ids.append(result.telemetry_id)
    async with open_scope(resources) as scope:
        telemetry = await PostgresTelemetryRepository(scope.session).get(ids[-1])  # type: ignore[arg-type]
        assert telemetry is not None
        context = await PostgisSpatialContextAnalyzer(scope.session).analyze(telemetry)
    assert 8 < context.displacement_window_m < 15


class _RecordingMqtt:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[str] = []

    async def publish_json(self, topic: str, payload: dict[str, object], *, retain: bool) -> None:
        if self.fail:
            raise ConnectionError("broker down")
        self.published.append(topic)


async def test_outbox_relay_publishes_in_order_and_survives_broker_outage(resources: AppResources) -> None:
    await _ongoing_trip(resources)
    down = _RecordingMqtt(fail=True)
    assert await OutboxRelay(resources.session_factory, down, OutboxSignal()).relay_once() == 0
    async with open_scope(resources) as scope:
        pending = await scope.session.scalar(select(func.count()).select_from(IntegrationOutboxModel))
        attempts = await scope.session.scalar(select(func.max(IntegrationOutboxModel.attempts)))
    assert pending == 1 and attempts == 1  # no se pierde nada mientras el broker está caído

    up = _RecordingMqtt()
    assert await OutboxRelay(resources.session_factory, up, OutboxSignal()).relay_once() == 1
    assert up.published == [TRIP_STARTED]
    async with open_scope(resources) as scope:
        assert await scope.session.scalar(select(func.count()).select_from(IntegrationOutboxModel)) == 0


async def test_reannounce_uses_trips_repository(resources: AppResources) -> None:
    await _ongoing_trip(resources)
    async with open_scope(resources) as scope:
        assert await trips_factory.reannounce_active_trips(scope).execute() == 1
