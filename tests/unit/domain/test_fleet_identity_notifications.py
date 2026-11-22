from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.modules.fleet.domain.entities.driver import DriverStatus
from app.modules.fleet.domain.entities.iot_device import ConnectionStatus
from app.modules.fleet.domain.entities.vehicle import VehicleStatus
from app.modules.fleet.domain.exceptions.fleet_errors import (
    DeviceNotAssignableError,
    DriverNotAvailableError,
    InvalidFleetDataError,
    InvalidFleetStatusChangeError,
    VehicleNotAvailableError,
)
from app.modules.identity.domain.entities.user import User
from app.modules.identity.domain.value_objects.email import Email
from app.modules.identity.domain.value_objects.role import Role
from app.modules.notifications.domain.entities.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)
from app.modules.notifications.domain.entities.notification_recipient import NotificationRecipient
from app.modules.notifications.domain.exceptions.notification_errors import (
    InvalidNotificationTransitionError,
    InvalidRecipientError,
)
from tests.unit.fakes import T0, make_driver, make_gateway, make_vehicle


def test_vehicle_code_is_normalised_and_validated() -> None:
    assert make_vehicle("trk-007").code == "TRK-007"
    with pytest.raises(InvalidFleetDataError):
        make_vehicle("x")


def test_vehicle_trip_lifecycle() -> None:
    vehicle = make_vehicle()
    vehicle.depart_on_trip()
    assert vehicle.status == VehicleStatus.ON_ROUTE
    with pytest.raises(VehicleNotAvailableError):
        vehicle.depart_on_trip()
    with pytest.raises(InvalidFleetStatusChangeError):
        vehicle.change_status(VehicleStatus.MAINTENANCE)
    vehicle.change_status(VehicleStatus.ON_ROUTE)  # si el formulario manda el mismo valor sin cambios, se acepta
    vehicle.return_from_trip()
    assert vehicle.status == VehicleStatus.AVAILABLE


def test_operator_cannot_put_vehicle_on_route_manually() -> None:
    with pytest.raises(InvalidFleetStatusChangeError):
        make_vehicle().change_status(VehicleStatus.ON_ROUTE)


def test_driver_assignment_rules() -> None:
    driver = make_driver()
    driver.assign_to_trip()
    assert driver.status == DriverStatus.ASSIGNED
    with pytest.raises(DriverNotAvailableError):
        driver.assign_to_trip()
    driver.release_from_trip()
    driver.change_status(DriverStatus.INACTIVE)
    with pytest.raises(DriverNotAvailableError):
        driver.ensure_available_for_trip()


def test_device_connection_status_is_derived() -> None:
    device = make_gateway()
    window = timedelta(seconds=180)
    assert device.connection_status(T0, window) == ConnectionStatus.OFFLINE
    device.record_connection(T0)
    device.record_connection(T0 - timedelta(hours=1))  # una marca de tiempo más vieja nunca lo hace retroceder
    assert device.last_connection_at == T0
    assert device.connection_status(T0 + timedelta(seconds=60), window) == ConnectionStatus.ONLINE
    assert device.connection_status(T0 + timedelta(seconds=600), window) == ConnectionStatus.OFFLINE
    device.deactivate()
    assert device.connection_status(T0, window) == ConnectionStatus.INACTIVE
    with pytest.raises(DeviceNotAssignableError):
        device.assign_to(uuid.uuid4())


def test_user_lockout_after_failed_attempts() -> None:
    user = User.register(
        email=Email("op@cargo.pe"), full_name="Operador Uno", password_hash="x", role=Role.OPERATOR, now=T0
    )
    for _ in range(5):
        user.record_failed_login(T0, max_attempts=5, lockout=timedelta(minutes=15))
    assert user.is_locked(T0 + timedelta(minutes=1))
    assert not user.can_authenticate(T0 + timedelta(minutes=1))
    assert user.can_authenticate(T0 + timedelta(minutes=16))


def test_recipient_validation_and_soft_delete() -> None:
    with pytest.raises(InvalidRecipientError):
        NotificationRecipient.register(name="Ana", telegram_chat_id="abc", now=T0)
    recipient = NotificationRecipient.register(name="Ana", telegram_chat_id="-100123", now=T0)
    recipient.remove(T0)
    assert not recipient.can_receive
    assert recipient.deleted_at == T0


def _notification() -> Notification:
    return Notification.prepare(
        monitoring_event_id=uuid.uuid4(),
        recipient_id=uuid.uuid4(),
        channel=NotificationChannel.TELEGRAM,
        destination="1",
        message="m",
        now=T0,
    )


def test_notification_records_attempts() -> None:
    notification = _notification()
    notification.record_failure(T0, "timeout", final=False)
    assert notification.status == NotificationStatus.PENDING
    notification.record_success(T0 + timedelta(seconds=2))
    assert notification.status == NotificationStatus.SENT
    assert notification.attempts == 2
    assert notification.sent_at == T0 + timedelta(seconds=2)
    with pytest.raises(InvalidNotificationTransitionError):
        notification.record_success(T0)


def test_notification_final_failure() -> None:
    notification = _notification()
    notification.record_failure(T0, "403 forbidden", final=True)
    assert notification.status == NotificationStatus.FAILED
    assert notification.error == "403 forbidden"
