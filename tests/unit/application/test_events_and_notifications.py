from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import timedelta

from app.modules.monitoring.application.dto.monitoring_dto import DetectedEventCommand, TripSummary
from app.modules.monitoring.application.use_cases.register_detected_event import RegisterDetectedEventUseCase
from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent, TelemetryKind
from app.modules.monitoring.domain.value_objects.temporal_classification import TemporalClassification
from app.modules.notifications.application.dto.notification_dto import EventNotificationRequest
from app.modules.notifications.application.use_cases.dispatch_event_notifications import (
    DispatchEventNotificationsUseCase,
    RetryPolicy,
)
from app.modules.notifications.domain.entities.notification import NotificationStatus
from app.modules.notifications.domain.entities.notification_recipient import NotificationRecipient
from app.modules.notifications.domain.exceptions.notification_errors import NotificationDeliveryError
from app.shared.domain.geo_point import GeoPoint
from tests.unit.fakes import (
    T0,
    FakeClock,
    FakeUnitOfWork,
    InMemoryMonitoringEventRepository,
    InMemoryNotificationRepository,
    InMemoryRecipientRepository,
    InMemoryTelemetryRepository,
    ScriptedGateway,
    StaticNotificationSettings,
    StaticTripDirectory,
    no_sleep,
)

TRIP_ID = uuid.uuid4()
SUMMARY = TripSummary(
    trip_id=TRIP_ID, trip_code="TRP-1", vehicle_code="TRK-001", driver_name="Ana Q", trip_status="ongoing"
)


def detected(**overrides: object) -> DetectedEventCommand:
    values: dict[str, object] = {
        "event_id": uuid.uuid4(),
        "event_type": "ROUTE_DEVIATION",
        "trip_id": TRIP_ID,
        "event_time": T0 + timedelta(minutes=3),
        "detected_at": T0 + timedelta(minutes=3, seconds=1),
        "started_at": T0,
        "latitude": -12.1,
        "longitude": -77.0,
        "evidence_from_sequence": 2,
        "evidence_to_sequence": 4,
        "metric_value": 450.0,
    }
    values.update(overrides)
    return DetectedEventCommand(**values)  # type: ignore[arg-type]


async def _telemetry_repository() -> InMemoryTelemetryRepository:
    repo = InMemoryTelemetryRepository()
    for seq in range(1, 6):
        await repo.add(
            TelemetryEvent.receive(
                message_id=uuid.uuid4(),
                device_id=uuid.uuid4(),
                trip_id=TRIP_ID,
                sequence=seq,
                event_time=T0 + timedelta(seconds=seq),
                received_at=T0 + timedelta(seconds=seq),
                position=GeoPoint(-12, -77),
                speed_kmh=40,
                kind=TelemetryKind.POSITION,
                temporal_classification=TemporalClassification.LIVE,
            )
        )
    return repo


async def test_register_detected_event_links_evidence_and_is_idempotent() -> None:
    events = InMemoryMonitoringEventRepository()
    use_case = RegisterDetectedEventUseCase(
        events,
        await _telemetry_repository(),
        StaticTripDirectory(SUMMARY),
        FakeUnitOfWork(),
        FakeClock(T0 + timedelta(minutes=4)),
    )
    command = detected()
    first = await use_case.execute(command)
    second = await use_case.execute(command)  # mismo event_id que manda el segundo consumidor / QoS 1
    assert first.created is True
    assert second.created is False
    stored = events.items[command.event_id]
    assert [e.sequence for e in stored.evidence] == [2, 3, 4]
    assert stored.details["duration_seconds"] == 180
    assert "450 m" in first.description
    assert first.severity == "HIGH"


async def _dispatch(
    gateway: ScriptedGateway, *, enabled: bool = True, max_attempts: int = 3
) -> tuple[InMemoryNotificationRepository, object]:
    recipient = NotificationRecipient.register(name="Ana", telegram_chat_id="123", now=T0)
    notifications = InMemoryNotificationRepository()
    use_case = DispatchEventNotificationsUseCase(
        recipients=InMemoryRecipientRepository([recipient], {TRIP_ID: [recipient.id]}),
        notifications=notifications,
        gateway=gateway,
        settings=StaticNotificationSettings(enabled),
        uow=FakeUnitOfWork(),
        clock=FakeClock(),
        retry_policy=RetryPolicy(max_attempts=max_attempts),
        sleep=no_sleep,
    )
    request = EventNotificationRequest(
        monitoring_event_id=uuid.uuid4(),
        trip_id=TRIP_ID,
        trip_code="TRP-1",
        vehicle_code="TRK-001",
        event_type="EMERGENCY",
        severity="CRITICAL",
        description="Botón de emergencia",
        detected_at=T0,
    )
    summary = await use_case.execute(request)
    again = await use_case.execute(request)  # una reentrega no puede mandar dos veces
    assert again.already_handled == 1
    return notifications, summary


async def test_notification_is_sent_after_transient_failure() -> None:
    gateway = ScriptedGateway([NotificationDeliveryError("timeout", retryable=True)])
    notifications, _ = await _dispatch(gateway)
    notification = next(iter(notifications.items.values()))
    assert notification.status == NotificationStatus.SENT
    assert notification.attempts == 2
    assert len(gateway.sent) == 1
    assert "CarGO | Emergencia" in gateway.sent[0][1]


async def test_telegram_outage_marks_notification_failed_but_keeps_event() -> None:
    gateway = ScriptedGateway([NotificationDeliveryError("503", retryable=True)] * 3)
    notifications, summary = await _dispatch(gateway)
    notification = next(iter(notifications.items.values()))
    assert notification.status == NotificationStatus.FAILED
    assert notification.attempts == 3
    assert notification.error == "503"
    assert summary.failed == 1  # type: ignore[attr-defined]


async def test_non_retryable_error_stops_immediately() -> None:
    gateway = ScriptedGateway([NotificationDeliveryError("403 bot blocked", retryable=False)])
    notifications, _ = await _dispatch(gateway)
    assert gateway.calls == 1
    assert next(iter(notifications.items.values())).status == NotificationStatus.FAILED


async def test_trip_started_alert_is_registered_once_despite_reannouncements() -> None:
    from datetime import UTC, datetime

    from app.modules.monitoring.application.trip_milestones import trip_started_command

    events = InMemoryMonitoringEventRepository()
    use_case = RegisterDetectedEventUseCase(
        events, await _telemetry_repository(), StaticTripDirectory(SUMMARY), FakeUnitOfWork(), FakeClock()
    )
    started = datetime(2026, 11, 10, 17, 0, tzinfo=UTC)

    def announcement() -> DetectedEventCommand:  # cada trip/started (inicio + reanuncios)
        return trip_started_command(
            trip_id=TRIP_ID,
            started_at=started,
            origin_latitude=-12.05,
            origin_longitude=-77.03,
            origin_label="Plaza San Martín",
            destination_label="Parque Kennedy",
        )

    first = await use_case.execute(announcement())
    again = await use_case.execute(announcement())
    assert first.created is True and again.created is False
    assert first.event_id == again.event_id and len(events.items) == 1
    assert first.event_type == "TRIP_STARTED" and first.severity == "INFO"
    assert first.description == "Inició el viaje: Plaza San Martín ➜ Parque Kennedy. Monitoreo en tiempo real activo."
    assert first.detected_at == started


def _connection_loss_request() -> EventNotificationRequest:
    from datetime import UTC, datetime

    return EventNotificationRequest(
        monitoring_event_id=uuid.uuid4(),
        trip_id=TRIP_ID,
        trip_code="TRP-261115-0C33",
        vehicle_code="TRK-003",
        driver_name="Carlos Mendoza",
        event_type="CONNECTION_LOSS",
        severity="HIGH",
        description="Sin telemetría en tiempo real durante 62 segundos.",
        detected_at=datetime(2026, 11, 15, 14, 44, 22, tzinfo=UTC),  # 09:44:22 en Lima (UTC-5)
        latitude=-12.032579,
        longitude=-77.138279,
    )


def test_telegram_message_has_the_uniform_html_format() -> None:
    from app.modules.notifications.application.notification_message_composer import NotificationMessageComposer

    message = NotificationMessageComposer("America/Lima").compose(_connection_loss_request())
    assert message.splitlines() == [
        "📡 <b>CarGO | Pérdida de comunicación</b>",
        "",  # separa el encabezado del contenido
        "<b>Viaje:</b> TRP-261115-0C33",
        "🚚 <b>Vehículo:</b> TRK-003",
        "<b>Conductor:</b> Carlos Mendoza",
        "<b>Detalle:</b> Sin telemetría en tiempo real durante 62 segundos.",
        "<b>Severidad:</b> Alta",
        "<b>Fecha:</b> 15/11/2026",
        "<b>Hora:</b> 09:44:22",
        '📍 <b>Última ubicación conocida:</b> <a href="https://maps.google.com/?q=-12.032579,-77.138279">'
        "Ver en Google Maps</a>",
    ]


def test_every_alert_type_keeps_its_emoji_and_the_same_layout() -> None:
    from app.modules.notifications.application.notification_message_composer import NotificationMessageComposer

    composer = NotificationMessageComposer()
    expected = {
        "TRIP_STARTED": ("🟢", "Viaje iniciado", "INFO", "Baja"),
        "ROUTE_DEVIATION": ("🧭", "Posible desviación", "HIGH", "Alta"),
        "PROLONGED_STOP": ("🛑", "Detención prolongada", "MEDIUM", "Media"),
        "DESTINATION_ARRIVAL": ("🏁", "Llegada al destino", "INFO", "Baja"),
        "EMERGENCY": ("🚨", "Emergencia", "CRITICAL", "Crítica"),
    }
    for event_type, (emoji, title, severity, label) in expected.items():
        lines = composer.compose(
            replace(_connection_loss_request(), event_type=event_type, severity=severity)
        ).splitlines()
        assert lines[0] == f"{emoji} <b>CarGO | {title}</b>"
        assert f"<b>Severidad:</b> {label}" in lines
        assert lines[-1].startswith("📍 <b>Ubicación:</b> <a href=")  # "Última ubicación" solo en CONNECTION_LOSS
        # Solo el encabezado, Vehículo y Ubicación llevan emoji.
        assert [line[0] for line in lines[2:-1] if not line.startswith("<b>")] == ["🚚"]


def test_alert_from_the_outage_shows_when_it_happened_and_when_it_was_detected() -> None:
    from datetime import UTC, datetime

    from app.modules.notifications.application.notification_message_composer import NotificationMessageComposer

    request = replace(
        _connection_loss_request(),
        event_type="PROLONGED_STOP",
        severity="MEDIUM",
        delayed=True,
        occurred_at=datetime(2026, 11, 15, 14, 10, 0, tzinfo=UTC),  # 09:10 en Lima: cuando pasó
    )
    lines = NotificationMessageComposer("America/Lima").compose(request).splitlines()
    assert lines[0] == "🛑 <b>CarGO | Detención prolongada (durante desconexión)</b>"
    assert "<b>Hora:</b> 09:10:00" in lines  # la hora real del hecho, no la de detección
    assert "<b>Detectada al reconectar:</b> 15/11/2026 09:44:22" in lines


def test_late_emergency_keeps_the_normal_title() -> None:
    from app.modules.notifications.application.notification_message_composer import NotificationMessageComposer

    request = replace(_connection_loss_request(), event_type="EMERGENCY", severity="CRITICAL", delayed=True)
    lines = NotificationMessageComposer().compose(request).splitlines()
    assert lines[0] == "🚨 <b>CarGO | Emergencia</b>"
    assert not any("Detectada al reconectar" in line for line in lines)


def test_description_explains_events_detected_after_reconnecting() -> None:
    from app.modules.monitoring.application.monitoring_event_describer import MonitoringEventDescriber

    describer = MonitoringEventDescriber()
    text = describer.describe("PROLONGED_STOP", {"delayed": True, "duration_seconds": 600})
    assert text.startswith("Detención prolongada de 10 min") and "mientras no había señal" in text
    assert "mientras no había señal" not in describer.describe("PROLONGED_STOP", {"delayed": False})


def test_dynamic_values_are_html_escaped() -> None:
    from app.modules.notifications.application.notification_message_composer import NotificationMessageComposer

    message = NotificationMessageComposer().compose(
        replace(_connection_loss_request(), driver_name="Ana <b>&</b>", description='Texto con "<a>"')
    )
    assert "<b>Conductor:</b> Ana &lt;b&gt;&amp;&lt;/b&gt;" in message
    assert "<b>Detalle:</b> Texto con &quot;&lt;a&gt;&quot;" in message


async def test_disabled_channel_is_skipped_and_recorded() -> None:
    gateway = ScriptedGateway()
    notifications, _ = await _dispatch(gateway, enabled=False)
    notification = next(iter(notifications.items.values()))
    assert notification.status == NotificationStatus.SKIPPED
    assert gateway.calls == 0
