from __future__ import annotations

import logging

from app.modules.monitoring.application.dto.monitoring_dto import (
    IngestionOutcome,
    IngestionResult,
    RawTelemetryCommand,
)
from app.modules.monitoring.application.ports.monitoring_ports import (
    DeviceConnectionRecorder,
    TelemetryContextProvider,
)
from app.modules.monitoring.application.services.telemetry_deduplicator import (
    DeduplicationVerdict,
    TelemetryDeduplicator,
)
from app.modules.monitoring.application.telemetry_integration_events import telemetry_normalized_event
from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent, TelemetryKind
from app.modules.monitoring.domain.exceptions.monitoring_errors import (
    TelemetryRejectedError,
    TelemetryRejectionReason,
)
from app.modules.monitoring.domain.repositories.monitoring_repositories import (
    DuplicateTelemetryError,
    TelemetryRepository,
)
from app.modules.monitoring.domain.services.telemetry_acceptance_policy import TelemetryAcceptancePolicy
from app.modules.monitoring.domain.services.temporal_classifier import TemporalClassifier
from app.shared.application.clock import Clock
from app.shared.application.event_publisher import EventPublisher
from app.shared.application.unit_of_work import UnitOfWork
from app.shared.domain.errors import DomainError
from app.shared.domain.geo_point import GeoPoint

logger = logging.getLogger("cargo.ingestion")


class IngestTelemetryUseCase:
    """Pipeline de ingesta: validar -> deduplicar -> clasificar -> guardar -> publicar normalizada.

    El guardado y la entrada del outbox de telemetry/normalized van en el mismo commit,
    así una lectura entra completa (y llega a CEP) o no entra.
    """

    def __init__(
        self,
        telemetry: TelemetryRepository,
        contexts: TelemetryContextProvider,
        connections: DeviceConnectionRecorder,
        deduplicator: TelemetryDeduplicator,
        policy: TelemetryAcceptancePolicy,
        classifier: TemporalClassifier,
        publisher: EventPublisher,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._telemetry = telemetry
        self._contexts = contexts
        self._connections = connections
        self._deduplicator = deduplicator
        self._policy = policy
        self._classifier = classifier
        self._publisher = publisher
        self._uow = uow
        self._clock = clock

    async def execute(self, command: RawTelemetryCommand) -> IngestionResult:
        try:
            return await self._ingest(command)
        except TelemetryRejectedError as rejection:
            await self._uow.rollback()
            logger.warning(
                "telemetry rejected",
                extra={
                    "device": command.device_code,
                    "message_id": str(command.message_id),
                    "reason": rejection.reason.value,
                },
            )
            return IngestionResult(IngestionOutcome.REJECTED, reason=rejection.reason.value)
        except DomainError as error:  # ej. coordenadas inválidas
            await self._uow.rollback()
            logger.warning("invalid telemetry", extra={"device": command.device_code, "error": error.message})
            return IngestionResult(IngestionOutcome.REJECTED, reason=TelemetryRejectionReason.INVALID_PAYLOAD.value)

    async def _ingest(self, command: RawTelemetryCommand) -> IngestionResult:
        if command.topic_device_code != command.device_code:
            raise TelemetryRejectedError(
                TelemetryRejectionReason.TOPIC_DEVICE_MISMATCH,
                "El device_id del mensaje no coincide con el topic de publicación.",
            )
        context = await self._contexts.load(device_code=command.device_code, trip_id=command.trip_id)
        if context is None:
            raise TelemetryRejectedError(TelemetryRejectionReason.UNKNOWN_DEVICE, "Dispositivo desconocido.")
        self._policy.ensure_acceptable(context, event_time=command.event_time, now=command.received_at)

        verdict = await self._deduplicator.assess(
            message_id=command.message_id, trip_id=command.trip_id, sequence=command.sequence
        )
        if verdict == DeduplicationVerdict.DUPLICATE_MESSAGE:
            logger.info("duplicate telemetry ignored", extra={"message_id": str(command.message_id)})
            return IngestionResult(IngestionOutcome.DUPLICATE, reason=verdict.value)
        if verdict == DeduplicationVerdict.SEQUENCE_CONFLICT:
            raise TelemetryRejectedError(
                TelemetryRejectionReason.SEQUENCE_CONFLICT,
                f"La secuencia {command.sequence} ya existe en el viaje con otro identificador.",
            )

        classification = self._classifier.classify(
            event_time=command.event_time,
            received_at=command.received_at,
            trip_is_ongoing=context.trip_is_ongoing,
        )
        telemetry = TelemetryEvent.receive(
            message_id=command.message_id,
            device_id=context.device_id,
            trip_id=command.trip_id,
            sequence=command.sequence,
            event_time=command.event_time,
            received_at=command.received_at,
            position=GeoPoint(command.latitude, command.longitude),
            speed_kmh=command.speed_kmh,
            kind=TelemetryKind.EMERGENCY if command.emergency else TelemetryKind.POSITION,
            temporal_classification=classification,
        )
        try:
            await self._telemetry.add(telemetry)
        except DuplicateTelemetryError:
            await self._uow.rollback()
            logger.info("duplicate telemetry (concurrent)", extra={"message_id": str(command.message_id)})
            return IngestionResult(IngestionOutcome.DUPLICATE, reason="unique_constraint")
        await self._connections.record(context.device_id, command.received_at)
        await self._publisher.publish(telemetry_normalized_event(telemetry, context))
        await self._uow.commit()
        logger.debug(
            "telemetry accepted",
            extra={"message_id": str(telemetry.message_id), "classification": classification.value},
        )
        return IngestionResult(
            IngestionOutcome.ACCEPTED,
            telemetry_id=telemetry.id,
            temporal_classification=classification.value,
        )
