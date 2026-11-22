from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from app.modules.fleet.domain.entities.driver import DriverStatus
from app.modules.fleet.domain.entities.vehicle import VehicleStatus
from app.modules.fleet.domain.exceptions.fleet_errors import VehicleNotAvailableError, VehicleWithoutDeviceError
from app.modules.trips.application.dto.trip_dto import CreateTripCommand
from app.modules.trips.application.use_cases.create_trip import CreateTripUseCase
from app.modules.trips.application.use_cases.trip_lifecycle import (
    CancelTripUseCase,
    FinishTripUseCase,
    ReannounceActiveTripsUseCase,
    StartTripUseCase,
    UpdateMonitoringConfigurationUseCase,
)
from app.modules.trips.domain.exceptions.trip_errors import (
    InvalidMonitoringConfigurationError,
    InvalidTripError,
    TripAlreadyStartedError,
    TripNotStartedError,
)
from app.modules.trips.domain.value_objects.trip_status import TripStatus
from app.shared.application.integration_topics import TRIP_CONFIG_UPDATED, TRIP_ENDED, TRIP_STARTED
from tests.unit.fakes import (
    FakeClock,
    FakeFleetAllocation,
    FakeUnitOfWork,
    InMemoryClientRepository,
    InMemoryMonitoringDefaults,
    InMemoryTripRepository,
    RecordingAuditLog,
    RecordingPublisher,
    StaticRecipientDirectory,
    make_driver,
    make_gateway,
    make_vehicle,
)

ACTOR = uuid.uuid4()
RECIPIENT = uuid.uuid4()


@dataclass
class Harness:
    trips: InMemoryTripRepository
    fleet: FakeFleetAllocation
    publisher: RecordingPublisher
    uow: FakeUnitOfWork
    clock: FakeClock
    audit: RecordingAuditLog

    def create(self) -> CreateTripUseCase:
        return CreateTripUseCase(
            trips=self.trips,
            clients=InMemoryClientRepository(),
            defaults=InMemoryMonitoringDefaults(),
            fleet=self.fleet,
            recipients=StaticRecipientDirectory({RECIPIENT}),
            uow=self.uow,
            clock=self.clock,
            audit=self.audit,
        )

    def start(self) -> StartTripUseCase:
        return StartTripUseCase(self.trips, self.fleet, self.publisher, self.uow, self.clock, self.audit)

    def finish(self) -> FinishTripUseCase:
        return FinishTripUseCase(self.trips, self.fleet, self.publisher, self.uow, self.clock, self.audit)

    def cancel(self) -> CancelTripUseCase:
        return CancelTripUseCase(self.trips, self.fleet, self.publisher, self.uow, self.clock, self.audit)


@pytest.fixture
def harness() -> Harness:
    fleet = FakeFleetAllocation(make_vehicle(), make_driver(), make_gateway())
    return Harness(
        InMemoryTripRepository(), fleet, RecordingPublisher(), FakeUnitOfWork(), FakeClock(), RecordingAuditLog()
    )


def command(**overrides: object) -> CreateTripCommand:
    values: dict[str, object] = {
        "vehicle_code": "TRK-001",
        "driver_code": "DRV-001",
        "origin_label": "Lima",
        "origin_latitude": -12.0464,
        "origin_longitude": -77.0428,
        "destination_label": "Ica",
        "destination_latitude": -14.0678,
        "destination_longitude": -75.7286,
        "cargo_description": "Cemento",
        "recipient_ids": frozenset({RECIPIENT}),
    }
    values.update(overrides)
    return CreateTripCommand(**values)  # type: ignore[arg-type]


async def test_create_trip_snapshots_configuration_without_planning_a_route(harness: Harness) -> None:
    code = await harness.create().execute(command(), actor_id=ACTOR)
    trip = await harness.trips.get_by_code(code)
    assert trip is not None
    assert trip.status == TripStatus.CONFIGURED
    assert (trip.origin.label, trip.destination.label) == ("Lima", "Ica")  # solo origen y destino
    assert trip.monitoring_configuration.connection_loss_seconds == 300
    assert harness.uow.commits == 1
    assert harness.publisher.events == []  # no se anuncia nada hasta que el viaje inicia
    assert "trip.created" in harness.audit.actions()


async def test_create_trip_rejects_unknown_recipient(harness: Harness) -> None:
    with pytest.raises(InvalidTripError):
        await harness.create().execute(command(recipient_ids=frozenset({uuid.uuid4()})), actor_id=ACTOR)
    assert harness.uow.commits == 0


async def test_create_trip_rejects_unavailable_vehicle(harness: Harness) -> None:
    harness.fleet.vehicle.change_status(VehicleStatus.MAINTENANCE)
    with pytest.raises(VehicleNotAvailableError):
        await harness.create().execute(command(), actor_id=ACTOR)


async def test_start_trip_reserves_fleet_and_publishes_trip_started(harness: Harness) -> None:
    code = await harness.create().execute(command(), actor_id=ACTOR)
    await harness.start().execute(code, actor_id=ACTOR)
    trip = await harness.trips.get_by_code(code)
    assert trip is not None and trip.status == TripStatus.ONGOING
    assert trip.device_id == harness.fleet.device.id  # type: ignore[union-attr]
    assert harness.fleet.vehicle.status == VehicleStatus.ON_ROUTE
    assert harness.fleet.driver.status == DriverStatus.ASSIGNED
    assert harness.publisher.topics() == [TRIP_STARTED]
    payload = harness.publisher.events[0].payload
    assert payload["trip_id"] == str(trip.id)
    assert payload["connection_loss_ms"] == 300_000


async def test_start_twice_is_rejected_without_side_effects(harness: Harness) -> None:
    code = await harness.create().execute(command(), actor_id=ACTOR)
    await harness.start().execute(code, actor_id=ACTOR)
    with pytest.raises(TripAlreadyStartedError):
        await harness.start().execute(code, actor_id=ACTOR)
    assert harness.publisher.topics() == [TRIP_STARTED]


async def test_start_requires_telemetry_gateway(harness: Harness) -> None:
    harness.fleet.device = None
    code = await harness.create().execute(command(), actor_id=ACTOR)
    with pytest.raises(VehicleWithoutDeviceError):
        await harness.start().execute(code, actor_id=ACTOR)


async def test_finish_releases_fleet_and_publishes_trip_ended(harness: Harness) -> None:
    code = await harness.create().execute(command(), actor_id=ACTOR)
    with pytest.raises(TripNotStartedError):
        await harness.finish().execute(code, actor_id=ACTOR)
    await harness.start().execute(code, actor_id=ACTOR)
    await harness.finish().execute(code, actor_id=ACTOR)
    trip = await harness.trips.get_by_code(code)
    assert trip is not None and trip.status == TripStatus.COMPLETED
    assert harness.fleet.vehicle.status == VehicleStatus.AVAILABLE
    assert harness.publisher.topics() == [TRIP_STARTED, TRIP_ENDED]
    assert harness.publisher.events[-1].payload["status"] == "completed"


async def test_finish_on_arrival_is_idempotent(harness: Harness) -> None:
    code = await harness.create().execute(command(), actor_id=ACTOR)
    await harness.start().execute(code, actor_id=ACTOR)
    trip = await harness.trips.get_by_code(code)
    assert trip is not None
    assert await harness.finish().finish_on_arrival(trip.id) is True
    assert await harness.finish().finish_on_arrival(trip.id) is False  # evento de llegada reentregado
    assert harness.publisher.topics().count(TRIP_ENDED) == 1


async def test_cancel_configured_trip_does_not_announce(harness: Harness) -> None:
    code = await harness.create().execute(command(), actor_id=ACTOR)
    await harness.cancel().execute(code, actor_id=ACTOR)
    assert harness.publisher.events == []


async def test_update_configuration_of_ongoing_trip_publishes_config_updated(harness: Harness) -> None:
    code = await harness.create().execute(command(), actor_id=ACTOR)
    await harness.start().execute(code, actor_id=ACTOR)
    use_case = UpdateMonitoringConfigurationUseCase(
        harness.trips, harness.publisher, harness.uow, harness.clock, harness.audit
    )
    await use_case.execute(code, {"stop_duration_seconds": 600}, actor_id=ACTOR)
    assert harness.publisher.topics()[-1] == TRIP_CONFIG_UPDATED
    assert harness.publisher.events[-1].payload["stop_duration_ms"] == 600_000
    with pytest.raises(InvalidMonitoringConfigurationError):
        await use_case.execute(code, {"connection_loss_seconds": 1}, actor_id=ACTOR)


async def test_reannounce_publishes_every_ongoing_trip(harness: Harness) -> None:
    code = await harness.create().execute(command(), actor_id=ACTOR)
    await harness.start().execute(code, actor_id=ACTOR)
    count = await ReannounceActiveTripsUseCase(harness.trips, harness.publisher, harness.uow, harness.clock).execute()
    assert count == 1
    assert harness.publisher.topics() == [TRIP_STARTED, TRIP_STARTED]
