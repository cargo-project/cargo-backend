from __future__ import annotations

import uuid

from app.modules.trips.domain.repositories.trip_repositories import MonitoringDefaultsRepository
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration
from app.shared.application.audit_log import AuditLog


class GetMonitoringDefaultsUseCase:
    def __init__(self, defaults: MonitoringDefaultsRepository) -> None:
        self._defaults = defaults

    async def execute(self) -> MonitoringConfiguration:
        return await self._defaults.get()


class UpdateMonitoringDefaultsUseCase:
    """Cambia la plantilla que se aplica a los viajes *nuevos*. Los existentes se quedan
    con su copia (para cambiar umbrales de un viaje en curso está
    UpdateMonitoringConfigurationUseCase).

    No hace commit: la pantalla de Configuración guarda los ajustes generales y los
    umbrales en una sola transacción que maneja quien llama.
    """

    def __init__(self, defaults: MonitoringDefaultsRepository, audit: AuditLog) -> None:
        self._defaults = defaults
        self._audit = audit

    async def execute(self, values: dict[str, float | int], *, actor_id: uuid.UUID) -> MonitoringConfiguration:
        configuration = MonitoringConfiguration().with_changes(**values)
        await self._defaults.save(configuration)
        await self._audit.record(
            action="settings.monitoring_defaults_changed",
            entity_type="settings",
            entity_id="monitoring_defaults",
            actor_id=actor_id,
            details=configuration.as_dict(),
        )
        return configuration
