from __future__ import annotations

import uuid
from enum import StrEnum

from app.modules.monitoring.domain.repositories.monitoring_repositories import TelemetryRepository


class DeduplicationVerdict(StrEnum):
    NEW = "new"
    DUPLICATE_MESSAGE = "duplicate_message"  # mismo message_id: reentrega QoS 1 o retransmisión
    SEQUENCE_CONFLICT = "sequence_conflict"  # misma (viaje, secuencia) pero con otro message_id


class TelemetryDeduplicator:
    """Control de idempotencia que corre ANTES de CEP (CEP nunca ve duplicados).

    La garantía final con concurrencia la dan las constraints únicas de la BD
    (message_id y (trip_id, sequence)); este chequeo ahorra trabajo y da un motivo claro.
    """

    def __init__(self, telemetry: TelemetryRepository) -> None:
        self._telemetry = telemetry

    async def assess(self, *, message_id: uuid.UUID, trip_id: uuid.UUID, sequence: int) -> DeduplicationVerdict:
        if await self._telemetry.exists_message(message_id):
            return DeduplicationVerdict.DUPLICATE_MESSAGE
        if await self._telemetry.exists_sequence(trip_id, sequence):
            return DeduplicationVerdict.SEQUENCE_CONFLICT
        return DeduplicationVerdict.NEW
