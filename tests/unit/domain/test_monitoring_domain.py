from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.modules.monitoring.domain.entities.monitoring_event import (
    MonitoringEvent,
    MonitoringEventStatus,
    Severity,
)
from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent, TelemetryKind
from app.modules.monitoring.domain.exceptions.monitoring_errors import (
    InvalidDetectedEventError,
    MonitoringEventAlreadyReviewedError,
    TelemetryRejectedError,
    TelemetryRejectionReason,
)
from app.modules.monitoring.domain.services.telemetry_acceptance_policy import (
    TelemetryAcceptancePolicy,
    TelemetryTripContext,
)
from app.modules.monitoring.domain.services.temporal_classifier import TemporalClassifier
from app.modules.monitoring.domain.services.vehicle_situation_classifier import (
    VehicleSituation,
    VehicleSituationClassifier,
    VehicleSnapshot,
)
from app.modules.monitoring.domain.value_objects.spatial_context import SpatialContext
from app.modules.monitoring.domain.value_objects.temporal_classification import TemporalClassification
from app.shared.domain.geo_point import GeoPoint
from tests.unit.fakes import T0

classifier = TemporalClassifier(timedelta(seconds=60))


def test_recent_measurement_is_live() -> None:
    result = classifier.classify(event_time=T0, received_at=T0 + timedelta(seconds=3), trip_is_ongoing=True)
    assert result == TemporalClassification.LIVE


def test_measurement_generated_1005_received_1031_is_delayed() -> None:
    generated = T0.replace(hour=10, minute=5)
    received = T0.replace(hour=10, minute=31)
    assert classifier.classify(event_time=generated, received_at=received, trip_is_ongoing=True) == (
        TemporalClassification.DELAYED
    )


def test_measurement_of_finished_trip_is_delayed_even_if_recent() -> None:
    result = classifier.classify(event_time=T0, received_at=T0, trip_is_ongoing=False)
    assert result == TemporalClassification.DELAYED


def _context(**overrides: object) -> TelemetryTripContext:
    device = uuid.uuid4()
    values: dict[str, object] = {
        "device_id": device,
        "device_code": "DEV-GW-001",
        "device_active": True,
        "trip_id": uuid.uuid4(),
        "trip_code": "TRP-1",
        "vehicle_code": "TRK-001",
        "trip_status": "ongoing",
        "trip_device_id": device,
        "trip_started_at": T0,
        "trip_ended_at": None,
    }
    values.update(overrides)
    return TelemetryTripContext(**values)  # type: ignore[arg-type]


policy = TelemetryAcceptancePolicy(max_future_skew=timedelta(seconds=120))


def test_acceptance_policy_accepts_valid_measurement() -> None:
    policy.ensure_acceptable(_context(), event_time=T0 + timedelta(minutes=1), now=T0 + timedelta(minutes=1))


@pytest.mark.parametrize(
    ("overrides", "event_offset", "reason"),
    [
        ({"device_active": False}, 0, TelemetryRejectionReason.DEVICE_INACTIVE),
        ({"trip_id": None, "trip_status": None}, 0, TelemetryRejectionReason.UNKNOWN_TRIP),
        ({"trip_device_id": uuid.uuid4()}, 0, TelemetryRejectionReason.DEVICE_TRIP_MISMATCH),
        ({"trip_status": "configured", "trip_started_at": None}, 0, TelemetryRejectionReason.TRIP_NOT_STARTED),
        ({}, 3600, TelemetryRejectionReason.FUTURE_TIMESTAMP),
        ({}, -3600, TelemetryRejectionReason.BEFORE_TRIP_START),
        (
            {"trip_status": "completed", "trip_ended_at": T0 + timedelta(minutes=10)},
            1800,
            TelemetryRejectionReason.AFTER_TRIP_END,
        ),
    ],
)
def test_acceptance_policy_rejections(
    overrides: dict[str, object], event_offset: int, reason: TelemetryRejectionReason
) -> None:
    with pytest.raises(TelemetryRejectedError) as error:
        policy.ensure_acceptable(
            _context(**overrides),
            event_time=T0 + timedelta(seconds=event_offset),
            now=T0 + timedelta(minutes=1) if event_offset != 1800 else T0 + timedelta(hours=1),
        )
    assert error.value.reason == reason


def _telemetry(**overrides: object) -> TelemetryEvent:
    values: dict[str, object] = {
        "message_id": uuid.uuid4(),
        "device_id": uuid.uuid4(),
        "trip_id": uuid.uuid4(),
        "sequence": 1,
        "event_time": T0,
        "received_at": T0 + timedelta(seconds=2),
        "position": GeoPoint(-12, -77),
        "speed_kmh": 50.0,
        "kind": TelemetryKind.POSITION,
        "temporal_classification": TemporalClassification.LIVE,
    }
    values.update(overrides)
    return TelemetryEvent.receive(**values)  # type: ignore[arg-type]


def test_telemetry_keeps_event_time_and_received_at() -> None:
    telemetry = _telemetry()
    assert telemetry.event_time == T0
    assert telemetry.transmission_lag_seconds == 2


@pytest.mark.parametrize("overrides", [{"speed_kmh": -1.0}, {"speed_kmh": 400.0}, {"sequence": -1}])
def test_telemetry_rejects_implausible_values(overrides: dict[str, object]) -> None:
    with pytest.raises(TelemetryRejectedError):
        _telemetry(**overrides)


def test_enrichment_is_applied_once() -> None:
    telemetry = _telemetry()
    first = SpatialContext(distance_to_destination_m=1000, inside_destination=False, moving_away_m=0.0)
    telemetry.enrich(first, T0)
    telemetry.enrich(SpatialContext(distance_to_destination_m=1, inside_destination=True), T0 + timedelta(seconds=1))
    assert telemetry.spatial_context == first
    assert telemetry.enriched_at == T0


def _detected(event_type: str = "ROUTE_DEVIATION") -> MonitoringEvent:
    return MonitoringEvent.detect(
        event_id=uuid.uuid4(),
        trip_id=uuid.uuid4(),
        event_type=event_type,
        event_time=T0,
        detected_at=T0 + timedelta(seconds=1),
        registered_at=T0 + timedelta(seconds=2),
        started_at=T0 - timedelta(minutes=2),
        position=None,
        details={},
        evidence=(),
    )


def test_severity_is_derived_from_type() -> None:
    assert _detected("EMERGENCY").severity == Severity.CRITICAL
    assert _detected("DESTINATION_ARRIVAL").severity == Severity.INFO
    assert _detected().detection_latency_seconds == 1


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(InvalidDetectedEventError):
        _detected("CONNECTION_RECOVERY")


def test_acknowledge_once() -> None:
    event = _detected()
    user = uuid.uuid4()
    event.acknowledge(user_id=user, now=T0)
    assert event.status == MonitoringEventStatus.REVIEWED
    assert event.reviewed_by == user
    with pytest.raises(MonitoringEventAlreadyReviewedError):
        event.acknowledge(user_id=user, now=T0)


def _snapshot(**overrides: object) -> VehicleSnapshot:
    values: dict[str, object] = {
        "has_pending_alert": False,
        "last_signal_at": T0,
        "speed_kmh": 60.0,
        "connection_loss_threshold": timedelta(seconds=300),
        "stop_speed_kmh": 3.0,
    }
    values.update(overrides)
    return VehicleSnapshot(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, VehicleSituation.ON_ROUTE),
        ({"speed_kmh": 0.0}, VehicleSituation.STOPPED),
        ({"last_signal_at": T0 - timedelta(minutes=10)}, VehicleSituation.NO_CONNECTION),
        ({"has_pending_alert": True, "speed_kmh": 0.0}, VehicleSituation.ALERT),
    ],
)
def test_vehicle_situation(overrides: dict[str, object], expected: VehicleSituation) -> None:
    assert VehicleSituationClassifier().classify(_snapshot(**overrides), T0) == expected
