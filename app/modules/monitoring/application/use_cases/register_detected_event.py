from __future__ import annotations

import logging
from typing import Any

from app.modules.monitoring.application.dto.monitoring_dto import (
    DetectedEventCommand,
    RegisteredEvent,
    TripSummary,
)
from app.modules.monitoring.application.monitoring_event_describer import MonitoringEventDescriber
from app.modules.monitoring.application.ports.monitoring_ports import MonitoringTripDirectory
from app.modules.monitoring.domain.entities.monitoring_event import (
    MonitoringEvent,
    MonitoringEventEvidence,
)
from app.modules.monitoring.domain.exceptions.monitoring_errors import InvalidDetectedEventError
from app.modules.monitoring.domain.repositories.monitoring_repositories import (
    MonitoringEventRepository,
    TelemetryRepository,
)
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.geo_point import GeoPoint

logger = logging.getLogger("cargo.monitoring")

MAX_EVIDENCE_ITEMS = 50


class RegisterDetectedEventUseCase:
    """Guarda un MonitoringEvent que viene de CEP, enlazado con la telemetría que lo respalda.

    events/detected lo consumen la API (tiempo real y llegada) y el servicio de notificaciones;
    el registro es idempotente por id, así que el primero que llega lo guarda y el otro lo
    reutiliza. Se guarda antes de intentar notificar: si Telegram falla, el evento no se pierde.
    """

    def __init__(
        self,
        events: MonitoringEventRepository,
        telemetry: TelemetryRepository,
        trips: MonitoringTripDirectory,
        uow: UnitOfWork,
        clock: Clock,
        describer: MonitoringEventDescriber | None = None,
    ) -> None:
        self._events = events
        self._telemetry = telemetry
        self._trips = trips
        self._uow = uow
        self._clock = clock
        self._describer = describer or MonitoringEventDescriber()

    async def execute(self, command: DetectedEventCommand) -> RegisteredEvent:
        trip = await self._trips.describe(command.trip_id)
        if trip is None:
            raise InvalidDetectedEventError(f"Evento para un viaje inexistente: {command.trip_id}")

        details = self._details(command)
        existing = await self._events.get(command.event_id)
        if existing is not None:
            return self._result(existing, trip, created=False)

        evidence: tuple[MonitoringEventEvidence, ...] = ()
        if command.evidence_from_sequence is not None and command.evidence_to_sequence is not None:
            low, high = sorted((command.evidence_from_sequence, command.evidence_to_sequence))
            evidence = await self._telemetry.evidence_between(command.trip_id, low, high, MAX_EVIDENCE_ITEMS)
        position = (
            GeoPoint(command.latitude, command.longitude)
            if command.latitude is not None
            and command.longitude is not None
            and not (command.latitude == 0 and command.longitude == 0)
            else None
        )
        event = MonitoringEvent.detect(
            event_id=command.event_id,
            trip_id=command.trip_id,
            event_type=command.event_type,
            event_time=command.event_time,
            detected_at=command.detected_at,
            registered_at=self._clock.now(),
            started_at=command.started_at,
            position=position,
            details=details,
            evidence=evidence,
        )
        created = await self._events.add_if_absent(event)
        await self._uow.commit()
        if created:
            logger.info(
                "monitoring event registered",
                extra={
                    "event_id": str(event.id),
                    "type": event.event_type.value,
                    "trip": trip.trip_code,
                    "detection_latency_s": round(event.detection_latency_seconds, 3),
                },
            )
        return self._result(event, trip, created=created)

    @staticmethod
    def _details(command: DetectedEventCommand) -> dict[str, Any]:
        details: dict[str, Any] = {"delayed": command.delayed, **command.extra_details}
        if command.metric_value is not None:
            details["metric_value"] = command.metric_value
        if command.started_at is not None:
            details["duration_seconds"] = round((command.event_time - command.started_at).total_seconds())
        if command.evidence_from_sequence is not None:
            details["evidence_sequences"] = [command.evidence_from_sequence, command.evidence_to_sequence]
        return details

    def _result(self, event: MonitoringEvent, trip: TripSummary, *, created: bool) -> RegisteredEvent:
        return RegisteredEvent(
            event_id=event.id,
            created=created,
            trip=trip,
            event_type=event.event_type.value,
            severity=event.severity.value,
            description=self._describer.describe(event.event_type.value, event.details),
            detected_at=event.detected_at,
            latitude=event.position.latitude if event.position else None,
            longitude=event.position.longitude if event.position else None,
            delayed=bool(event.details.get("delayed")),
            occurred_at=event.started_at or event.event_time,
        )
