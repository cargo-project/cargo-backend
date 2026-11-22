from __future__ import annotations

import uuid
from typing import Protocol

from app.modules.monitoring.domain.entities.monitoring_event import (
    MonitoringEvent,
    MonitoringEventEvidence,
)
from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent


class TelemetryRepository(Protocol):
    async def exists_message(self, message_id: uuid.UUID) -> bool: ...

    async def exists_sequence(self, trip_id: uuid.UUID, sequence: int) -> bool: ...

    async def get(self, telemetry_id: uuid.UUID) -> TelemetryEvent | None: ...

    async def add(self, telemetry: TelemetryEvent) -> None:
        """Lanza DuplicateTelemetryError si salta una constraint única (duplicado concurrente)."""
        ...

    async def save_enrichment(self, telemetry: TelemetryEvent) -> None: ...

    async def evidence_between(
        self, trip_id: uuid.UUID, from_sequence: int, to_sequence: int, limit: int
    ) -> tuple[MonitoringEventEvidence, ...]: ...


class DuplicateTelemetryError(Exception):
    """Señal de infraestructura: la BD rechazó una lectura duplicada."""


class MonitoringEventRepository(Protocol):
    async def get(self, event_id: uuid.UUID) -> MonitoringEvent | None: ...

    async def add_if_absent(self, event: MonitoringEvent) -> bool:
        """Inserta el evento si su id no existe todavía. Devuelve True si lo insertó."""
        ...

    async def save(self, event: MonitoringEvent) -> None: ...
