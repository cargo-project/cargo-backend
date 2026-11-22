from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from app.modules.configuration.application.ports import (
    IntegrationProbe,
    IntegrationStatus,
    MonitoringDefaultsGateway,
)
from app.modules.configuration.domain.system_settings import (
    DistanceUnit,
    InvalidSettingsError,
    Language,
    SystemSettings,
    SystemSettingsRepository,
)
from app.shared.application.audit_log import AuditLog
from app.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class SettingsView:
    general: SystemSettings
    monitoring: dict[str, float | int]


@dataclass(frozen=True, slots=True)
class GeneralSettingsData:
    organization_name: str
    timezone: str
    distance_unit: str
    default_language: str
    telegram_enabled: bool


class GetSettingsUseCase:
    def __init__(self, settings: SystemSettingsRepository, defaults: MonitoringDefaultsGateway) -> None:
        self._settings = settings
        self._defaults = defaults

    async def execute(self) -> SettingsView:
        return SettingsView(general=await self._settings.get(), monitoring=await self._defaults.get())


class UpdateSettingsUseCase:
    """Guarda la pantalla de Configuración de una sola vez: ajustes generales + umbrales por defecto."""

    def __init__(
        self,
        settings: SystemSettingsRepository,
        defaults: MonitoringDefaultsGateway,
        uow: UnitOfWork,
        audit: AuditLog,
    ) -> None:
        self._settings = settings
        self._defaults = defaults
        self._uow = uow
        self._audit = audit

    async def execute(
        self, general: GeneralSettingsData, monitoring: dict[str, float | int], *, actor_id: uuid.UUID
    ) -> SettingsView:
        try:
            settings = SystemSettings(
                organization_name=general.organization_name,
                timezone=general.timezone,
                distance_unit=DistanceUnit(general.distance_unit),
                default_language=Language(general.default_language),
                telegram_enabled=general.telegram_enabled,
            )
        except ValueError as error:
            raise InvalidSettingsError(str(error)) from error
        await self._settings.save(settings)
        updated_defaults = await self._defaults.update(monitoring, actor_id=actor_id)
        await self._audit.record(
            action="settings.general_changed",
            entity_type="settings",
            entity_id="general",
            actor_id=actor_id,
            details={"telegram_enabled": settings.telegram_enabled},
        )
        await self._uow.commit()
        return SettingsView(general=settings, monitoring=updated_defaults)


class CheckIntegrationHealthUseCase:
    """Corre los chequeos reales en paralelo; ninguno dice "online" sin haber probado."""

    def __init__(self, probes: list[IntegrationProbe]) -> None:
        self._probes = probes

    async def execute(self) -> list[IntegrationStatus]:
        return list(await asyncio.gather(*(probe.check() for probe in self._probes)))
