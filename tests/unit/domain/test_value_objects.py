from __future__ import annotations

import pytest

from app.modules.identity.domain.exceptions.identity_errors import InvalidEmailError, WeakPasswordError
from app.modules.identity.domain.services.password_policy import PasswordPolicy
from app.modules.identity.domain.value_objects.email import Email
from app.modules.trips.domain.exceptions.trip_errors import InvalidMonitoringConfigurationError
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration
from app.shared.domain.geo_point import GeoPoint, InvalidCoordinatesError


@pytest.mark.parametrize(("lat", "lon"), [(91, 0), (-91, 0), (0, 181), (0, -181), (float("nan"), 0)])
def test_geo_point_rejects_out_of_range(lat: float, lon: float) -> None:
    with pytest.raises(InvalidCoordinatesError):
        GeoPoint(lat, lon)


def test_geo_point_distance_lima_ica_is_plausible() -> None:
    distance = GeoPoint(-12.0464, -77.0428).approximate_distance_m(GeoPoint(-14.0678, -75.7286))
    assert 260_000 < distance < 270_000


def test_geo_point_lon_lat_order() -> None:
    assert GeoPoint(1.5, 2.5).as_lon_lat() == (2.5, 1.5)


def test_monitoring_configuration_defaults_are_valid() -> None:
    config = MonitoringConfiguration()
    assert config.route_deviation_min_events == 3
    assert config.route_deviation_min_increase_m == 300  # alejarse del destino
    assert config.as_dict()["connection_loss_seconds"] == 300
    assert "route_deviation_corridor_m" not in config.as_dict()  # sin ruta, sin corredor


def test_monitoring_configuration_ignores_legacy_corridor_when_loaded() -> None:
    stored = {**MonitoringConfiguration().as_dict(), "route_deviation_corridor_m": 200.0}
    assert MonitoringConfiguration.from_stored(stored) == MonitoringConfiguration()


@pytest.mark.parametrize(
    "changes",
    [
        {"route_deviation_min_events": 1},
        {"connection_loss_seconds": 5},
        {"stop_speed_kmh": 80},
        {"arrival_radius_m": 1},
        {"route_deviation_min_increase_m": 0},  # con 0 m saltaría con el ruido del GPS
    ],
)
def test_monitoring_configuration_rejects_unsafe_values(changes: dict[str, float]) -> None:
    with pytest.raises(InvalidMonitoringConfigurationError):
        MonitoringConfiguration().with_changes(**changes)


def test_monitoring_configuration_rejects_unknown_parameter() -> None:
    with pytest.raises(InvalidMonitoringConfigurationError):
        MonitoringConfiguration().with_changes(speed_limit=90)


def test_monitoring_configuration_is_immutable_value() -> None:
    original = MonitoringConfiguration()
    changed = original.with_changes(stop_duration_seconds=600)
    assert original.stop_duration_seconds == 900
    assert changed.stop_duration_seconds == 600
    assert original != changed


def test_email_is_normalised() -> None:
    assert Email("  Admin@CarGO.pe ").value == "admin@cargo.pe"


@pytest.mark.parametrize("raw", ["", "no-at", "a@b", "a b@c.pe"])
def test_email_rejects_invalid(raw: str) -> None:
    with pytest.raises(InvalidEmailError):
        Email(raw)


def test_password_policy() -> None:
    PasswordPolicy.validate("una-frase-larga-segura")
    with pytest.raises(WeakPasswordError):
        PasswordPolicy.validate("corta")
    with pytest.raises(WeakPasswordError):
        PasswordPolicy.validate("admin@cargo.pe", email="admin@cargo.pe")
