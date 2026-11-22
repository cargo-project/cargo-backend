from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.modules.trips.domain.entities.trip import Trip
from app.modules.trips.domain.exceptions.trip_errors import (
    InvalidTripError,
    TripAlreadyFinishedError,
    TripAlreadyStartedError,
    TripNotStartedError,
)
from app.modules.trips.domain.value_objects.location import Location
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration
from app.modules.trips.domain.value_objects.trip_status import TripStatus
from app.shared.domain.geo_point import GeoPoint
from tests.unit.fakes import T0

ORIGIN = GeoPoint(-12.0464, -77.0428)
DESTINATION = GeoPoint(-14.0678, -75.7286)


def make_trip(**overrides: object) -> Trip:
    arguments: dict[str, object] = {
        "code": "TRP-1",
        "vehicle_id": uuid.uuid4(),
        "driver_id": uuid.uuid4(),
        "origin": Location("Lima", ORIGIN),
        "destination": Location("Ica", DESTINATION),
        "cargo_description": "Cemento 30 t",
        "monitoring_configuration": MonitoringConfiguration(),
        "recipient_ids": frozenset({uuid.uuid4()}),
        "now": T0,
    }
    arguments.update(overrides)
    return Trip.plan(**arguments)  # type: ignore[arg-type]


def test_new_trip_is_configured() -> None:
    trip = make_trip()
    assert trip.status == TripStatus.CONFIGURED
    assert not trip.is_monitored
    assert trip.started_at is None


def test_start_moves_to_ongoing_and_records_device() -> None:
    trip = make_trip()
    device = uuid.uuid4()
    trip.start(now=T0 + timedelta(minutes=5), device_id=device)
    assert trip.status == TripStatus.ONGOING
    assert trip.device_id == device
    assert trip.started_at == T0 + timedelta(minutes=5)
    assert trip.is_monitored


def test_cannot_start_twice() -> None:
    trip = make_trip()
    trip.start(now=T0, device_id=uuid.uuid4())
    with pytest.raises(TripAlreadyStartedError):
        trip.start(now=T0, device_id=uuid.uuid4())


def test_cannot_finish_before_starting() -> None:
    with pytest.raises(TripNotStartedError):
        make_trip().finish(now=T0)


def test_finish_completes_trip() -> None:
    trip = make_trip()
    trip.start(now=T0, device_id=uuid.uuid4())
    trip.finish(now=T0 + timedelta(hours=4), reason="destination_arrival")
    assert trip.status == TripStatus.COMPLETED
    assert trip.ended_at == T0 + timedelta(hours=4)
    assert trip.end_reason == "destination_arrival"


@pytest.mark.parametrize("terminal", ["finish", "cancel"])
def test_terminal_trip_rejects_any_change(terminal: str) -> None:
    trip = make_trip()
    trip.start(now=T0, device_id=uuid.uuid4())
    getattr(trip, terminal)(now=T0)
    with pytest.raises(TripAlreadyFinishedError):
        trip.start(now=T0, device_id=uuid.uuid4())
    with pytest.raises(TripAlreadyFinishedError):
        trip.cancel(now=T0)
    with pytest.raises(TripAlreadyFinishedError):
        trip.update_monitoring_configuration(MonitoringConfiguration())


def test_configured_trip_can_be_cancelled() -> None:
    trip = make_trip()
    trip.cancel(now=T0)
    assert trip.status == TripStatus.CANCELLED
    assert trip.cancelled_at == T0


def test_origin_and_destination_must_differ() -> None:
    with pytest.raises(InvalidTripError):
        make_trip(destination=Location("Lima centro", GeoPoint(-12.0465, -77.0429)))


def test_requires_at_least_one_recipient() -> None:
    with pytest.raises(InvalidTripError):
        make_trip(recipient_ids=frozenset())


def test_requires_cargo_description() -> None:
    with pytest.raises(InvalidTripError):
        make_trip(cargo_description="  ")


def test_status_cannot_be_assigned_through_transitions_table() -> None:
    assert not TripStatus.COMPLETED.can_transition_to(TripStatus.ONGOING)
    assert not TripStatus.CONFIGURED.can_transition_to(TripStatus.COMPLETED)
    assert TripStatus.ONGOING.can_transition_to(TripStatus.CANCELLED)


def test_trip_is_only_origin_and_destination() -> None:
    trip = make_trip()
    assert not hasattr(trip, "planned_route")  # CarGO nunca propone ni guarda una ruta
