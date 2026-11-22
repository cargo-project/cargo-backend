from __future__ import annotations

import logging

from app.modules.monitoring.application.dto.monitoring_dto import NormalizedTelemetry
from app.modules.monitoring.application.ports.monitoring_ports import SpatialContextAnalyzer
from app.modules.monitoring.application.telemetry_integration_events import telemetry_enriched_event
from app.modules.monitoring.domain.repositories.monitoring_repositories import TelemetryRepository
from app.shared.application.clock import Clock
from app.shared.application.event_publisher import EventPublisher
from app.shared.application.unit_of_work import UnitOfWork

logger = logging.getLogger("cargo.geospatial")


class EnrichTelemetryUseCase:
    """Le agrega contexto espacial a una lectura normalizada y publica telemetry/enriched.

    No decide anomalías, no corre reglas CEP ni notifica a nadie.
    Idempotente: si llega de nuevo una lectura ya enriquecida, se ignora.
    """

    def __init__(
        self,
        telemetry: TelemetryRepository,
        analyzer: SpatialContextAnalyzer,
        publisher: EventPublisher,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._telemetry = telemetry
        self._analyzer = analyzer
        self._publisher = publisher
        self._uow = uow
        self._clock = clock

    async def execute(self, message: NormalizedTelemetry) -> bool:
        telemetry = await self._telemetry.get(message.telemetry_id)
        if telemetry is None:
            logger.warning("normalized telemetry not found", extra={"telemetry_id": str(message.telemetry_id)})
            return False
        if telemetry.is_enriched:
            logger.info("telemetry already enriched", extra={"telemetry_id": str(telemetry.id)})
            return False
        context = await self._analyzer.analyze(telemetry)
        telemetry.enrich(context, self._clock.now())
        await self._telemetry.save_enrichment(telemetry)
        await self._publisher.publish(telemetry_enriched_event(telemetry, message.payload))
        await self._uow.commit()
        return True
