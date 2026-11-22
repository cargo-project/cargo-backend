"""Dobles de prueba en memoria para los puertos. Cumplen los mismos Protocols que los
adaptadores de PostgreSQL, por eso se pueden probar los casos de uso sin base de datos.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.fleet.domain.entities.assignments import VehicleDriverAssignment
from app.modules.fleet.domain.entities.driver import Driver, DriverStatus
from app.modules.fleet.domain.entities.iot_device import IoTDevice, IoTDeviceType
from app.modules.fleet.domain.entities.vehicle import Vehicle, VehicleStatus
from app.modules.fleet.domain.exceptions.fleet_errors import VehicleWithoutDeviceError
from app.modules.monitoring.application.dto.monitoring_dto import TripSummary
from app.modules.monitoring.domain.entities.monitoring_event import MonitoringEvent, MonitoringEventEvidence
from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent
from app.modules.monitoring.domain.services.telemetry_acceptance_policy import TelemetryTripContext
from app.modules.notifications.domain.entities.notification import Notification
from app.modules.notifications.domain.entities.notification_recipient import NotificationRecipient
from app.modules.notifications.domain.exceptions.notification_errors import NotificationDeliveryError
from app.modules.trips.application.ports.fleet_allocation import PlanningResources
from app.modules.trips.domain.entities.client import Client
from app.modules.trips.domain.entities.trip import Trip
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration
from app.modules.trips.domain.value_objects.trip_status import TripStatus
from app.shared.application.event_publisher import IntegrationEvent

T0 = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = T0) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[IntegrationEvent] = []

    async def publish(self, event: IntegrationEvent) -> None:
        self.events.append(event)

    def topics(self) -> list[str]:
        return [event.topic for event in self.events]


class RecordingAuditLog:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def record(self, **entry: Any) -> None:
        self.entries.append(entry)

    def actions(self) -> list[str]:
        return [entry["action"] for entry in self.entries]


# ----------------------------------------------------------------------------- viajes
class InMemoryTripRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Trip] = {}

    async def get_by_id(self, trip_id: uuid.UUID) -> Trip | None:
        trip = self.items.get(trip_id)
        return copy.deepcopy(trip) if trip else None

    async def get_by_code(self, code: str) -> Trip | None:
        return next((copy.deepcopy(t) for t in self.items.values() if t.code == code), None)

    async def code_exists(self, code: str) -> bool:
        return any(t.code == code for t in self.items.values())

    async def list_ongoing(self) -> list[Trip]:
        return [copy.deepcopy(t) for t in self.items.values() if t.status == TripStatus.ONGOING]

    async def add(self, trip: Trip) -> None:
        self.items[trip.id] = copy.deepcopy(trip)

    async def save(self, trip: Trip) -> None:
        self.items[trip.id] = copy.deepcopy(trip)


class InMemoryClientRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Client] = {}

    async def get_by_id(self, client_id: uuid.UUID) -> Client | None:
        return self.items.get(client_id)

    async def list_all(self) -> list[Client]:
        return list(self.items.values())

    async def add(self, client: Client) -> None:
        self.items[client.id] = client


class InMemoryMonitoringDefaults:
    def __init__(self, configuration: MonitoringConfiguration | None = None) -> None:
        self.configuration = configuration or MonitoringConfiguration()

    async def get(self) -> MonitoringConfiguration:
        return self.configuration

    async def save(self, configuration: MonitoringConfiguration) -> None:
        self.configuration = configuration


class StaticRecipientDirectory:
    def __init__(self, active: set[uuid.UUID]) -> None:
        self.active = active

    async def find_missing_or_inactive(self, recipient_ids: frozenset[uuid.UUID]) -> set[uuid.UUID]:
        return set(recipient_ids) - self.active


# ----------------------------------------------------------------------------- flota
class InMemoryVehicleRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Vehicle] = {}

    async def get_by_id(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        return self.items.get(vehicle_id)

    async def get_by_code(self, code: str) -> Vehicle | None:
        return next((v for v in self.items.values() if v.code == code), None)

    async def exists_with_plate(self, plate: str, *, excluding: uuid.UUID | None = None) -> bool:
        return any(v.plate == plate and v.id != excluding for v in self.items.values())

    async def add(self, vehicle: Vehicle) -> None:
        self.items[vehicle.id] = vehicle

    async def save(self, vehicle: Vehicle) -> None:
        self.items[vehicle.id] = vehicle


class InMemoryDriverRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Driver] = {}

    async def get_by_id(self, driver_id: uuid.UUID) -> Driver | None:
        return self.items.get(driver_id)

    async def get_by_code(self, code: str) -> Driver | None:
        return next((d for d in self.items.values() if d.code == code), None)

    async def exists_with_document(self, document: str, *, excluding: uuid.UUID | None = None) -> bool:
        return any(d.document_number == document and d.id != excluding for d in self.items.values())

    async def add(self, driver: Driver) -> None:
        self.items[driver.id] = driver

    async def save(self, driver: Driver) -> None:
        self.items[driver.id] = driver


class InMemoryDeviceRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, IoTDevice] = {}

    async def get_by_id(self, device_id: uuid.UUID) -> IoTDevice | None:
        return self.items.get(device_id)

    async def get_by_code(self, code: str) -> IoTDevice | None:
        return next((d for d in self.items.values() if d.code == code), None)

    async def find_active_gateway_for_vehicle(self, vehicle_id: uuid.UUID) -> IoTDevice | None:
        return next(
            (
                d
                for d in self.items.values()
                if d.vehicle_id == vehicle_id and d.is_active and d.device_type == IoTDeviceType.EDGE_GATEWAY
            ),
            None,
        )

    async def add(self, device: IoTDevice) -> None:
        self.items[device.id] = device

    async def save(self, device: IoTDevice) -> None:
        self.items[device.id] = device


class InMemoryDeviceAssignments:
    def __init__(self) -> None:
        self.items: list[Any] = []

    async def get_open_for_device(self, device_id: uuid.UUID) -> Any:
        return next((a for a in self.items if a.device_id == device_id and a.released_at is None), None)

    async def add(self, assignment: Any) -> None:
        self.items.append(assignment)

    async def save(self, assignment: Any) -> None:
        return None


class FakeFleetAllocation:
    """Adaptador de flota simplificado: mismas reglas que el real, pero en memoria."""

    def __init__(self, vehicle: Vehicle, driver: Driver, device: IoTDevice | None) -> None:
        self.vehicle, self.driver, self.device = vehicle, driver, device
        self.assignments: list[VehicleDriverAssignment] = []

    async def resolve_for_planning(self, *, vehicle_code: str, driver_code: str) -> PlanningResources:
        self.vehicle.ensure_available_for_trip()
        self.driver.ensure_available_for_trip()
        return PlanningResources(vehicle_id=self.vehicle.id, driver_id=self.driver.id)

    async def allocate(
        self, *, trip_id: uuid.UUID, vehicle_id: uuid.UUID, driver_id: uuid.UUID, now: datetime
    ) -> uuid.UUID:
        if self.device is None:
            raise VehicleWithoutDeviceError("sin gateway")
        self.vehicle.depart_on_trip()
        self.driver.assign_to_trip()
        self.assignments.append(
            VehicleDriverAssignment.open(vehicle_id=vehicle_id, driver_id=driver_id, trip_id=trip_id, now=now)
        )
        return self.device.id

    async def release(self, *, trip_id: uuid.UUID, vehicle_id: uuid.UUID, driver_id: uuid.UUID, now: datetime) -> None:
        self.vehicle.return_from_trip()
        self.driver.release_from_trip()


def make_vehicle(code: str = "TRK-001") -> Vehicle:
    return Vehicle.register(
        code=code,
        plate=f"P{code[-3:]}-XYZ",
        brand="Volvo",
        model="FH",
        description="",
        status=VehicleStatus.AVAILABLE,
        now=T0,
    )


def make_driver(code: str = "DRV-001") -> Driver:
    return Driver.register(
        code=code,
        first_name="Ana",
        last_name="Quispe",
        document_number=f"4{code[-3:]}5678",
        license_number="Q12345",
        phone="999888777",
        status=DriverStatus.AVAILABLE,
        now=T0,
    )


def make_gateway(code: str = "DEV-GW-001") -> IoTDevice:
    return IoTDevice.register(
        code=code,
        device_type=IoTDeviceType.EDGE_GATEWAY,
        serial_number="EGW-0001",
        firmware_version="2.0.0",
        is_active=True,
        now=T0,
    )


# ----------------------------------------------------------------------------- monitoreo
class InMemoryTelemetryRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, TelemetryEvent] = {}

    async def exists_message(self, message_id: uuid.UUID) -> bool:
        return any(t.message_id == message_id for t in self.items.values())

    async def exists_sequence(self, trip_id: uuid.UUID, sequence: int) -> bool:
        return any(t.trip_id == trip_id and t.sequence == sequence for t in self.items.values())

    async def get(self, telemetry_id: uuid.UUID) -> TelemetryEvent | None:
        item = self.items.get(telemetry_id)
        return copy.deepcopy(item) if item else None

    async def add(self, telemetry: TelemetryEvent) -> None:
        self.items[telemetry.id] = copy.deepcopy(telemetry)

    async def save_enrichment(self, telemetry: TelemetryEvent) -> None:
        self.items[telemetry.id] = copy.deepcopy(telemetry)

    async def evidence_between(
        self, trip_id: uuid.UUID, from_sequence: int, to_sequence: int, limit: int
    ) -> tuple[MonitoringEventEvidence, ...]:
        matches = sorted(
            (t for t in self.items.values() if t.trip_id == trip_id and from_sequence <= t.sequence <= to_sequence),
            key=lambda t: t.sequence,
        )[-limit:]
        return tuple(MonitoringEventEvidence(t.id, t.sequence) for t in matches)


@dataclass
class StaticTelemetryContextProvider:
    context: TelemetryTripContext | None

    async def load(self, *, device_code: str, trip_id: uuid.UUID) -> TelemetryTripContext | None:
        if self.context is None or self.context.device_code != device_code:
            return None
        return self.context


@dataclass
class RecordingConnections:
    calls: list[tuple[uuid.UUID, datetime]] = field(default_factory=list)

    async def record(self, device_id: uuid.UUID, at: datetime) -> None:
        self.calls.append((device_id, at))


class InMemoryMonitoringEventRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, MonitoringEvent] = {}

    async def get(self, event_id: uuid.UUID) -> MonitoringEvent | None:
        return self.items.get(event_id)

    async def add_if_absent(self, event: MonitoringEvent) -> bool:
        if event.id in self.items:
            return False
        self.items[event.id] = event
        return True

    async def save(self, event: MonitoringEvent) -> None:
        self.items[event.id] = event


@dataclass
class StaticTripDirectory:
    summary: TripSummary | None

    async def describe(self, trip_id: uuid.UUID) -> TripSummary | None:
        return self.summary if self.summary and self.summary.trip_id == trip_id else None


# ----------------------------------------------------------------------------- notificaciones
class InMemoryRecipientRepository:
    def __init__(self, recipients: list[NotificationRecipient], trip_links: dict[uuid.UUID, list[uuid.UUID]]) -> None:
        self.items = {r.id: r for r in recipients}
        self.trip_links = trip_links

    async def get_by_id(self, recipient_id: uuid.UUID) -> NotificationRecipient | None:
        return self.items.get(recipient_id)

    async def list_visible(self) -> list[NotificationRecipient]:
        return [r for r in self.items.values() if r.deleted_at is None]

    async def exists_with_chat_id(self, chat_id: str) -> bool:
        return any(r.telegram_chat_id == chat_id and r.deleted_at is None for r in self.items.values())

    async def recipients_of_trip(self, trip_id: uuid.UUID) -> list[NotificationRecipient]:
        return [self.items[rid] for rid in self.trip_links.get(trip_id, [])]

    async def add(self, recipient: NotificationRecipient) -> None:
        self.items[recipient.id] = recipient

    async def save(self, recipient: NotificationRecipient) -> None:
        self.items[recipient.id] = recipient


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Notification] = {}

    async def find(self, monitoring_event_id: uuid.UUID, recipient_id: uuid.UUID) -> Notification | None:
        return next(
            (
                n
                for n in self.items.values()
                if n.monitoring_event_id == monitoring_event_id and n.recipient_id == recipient_id
            ),
            None,
        )

    async def list_for_event(self, monitoring_event_id: uuid.UUID) -> list[Notification]:
        return [n for n in self.items.values() if n.monitoring_event_id == monitoring_event_id]

    async def add(self, notification: Notification) -> None:
        self.items[notification.id] = notification

    async def save(self, notification: Notification) -> None:
        self.items[notification.id] = notification


class ScriptedGateway:
    """Falla con los errores programados (en orden) y después funciona."""

    def __init__(self, failures: list[NotificationDeliveryError] | None = None, configured: bool = True) -> None:
        self.failures = list(failures or [])
        self.sent: list[tuple[str, str]] = []
        self.configured = configured
        self.calls = 0

    @property
    def is_configured(self) -> bool:
        return self.configured

    async def send(self, destination: str, message: str) -> None:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        self.sent.append((destination, message))


@dataclass
class StaticNotificationSettings:
    enabled: bool = True

    async def telegram_enabled(self) -> bool:
        return self.enabled


async def no_sleep(_: float) -> None:
    return None
