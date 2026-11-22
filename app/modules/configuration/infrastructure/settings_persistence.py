from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.modules.configuration.domain.system_settings import DistanceUnit, Language, SystemSettings
from app.modules.trips.application.use_cases.monitoring_defaults_use_cases import (
    GetMonitoringDefaultsUseCase,
    UpdateMonitoringDefaultsUseCase,
)

_ROW_ID = 1


class SystemSettingsModel(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64))
    distance_unit: Mapped[str] = mapped_column(String(4))
    default_language: Mapped[str] = mapped_column(String(4))
    telegram_enabled: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PostgresSystemSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> SystemSettings:
        model = await self._session.get(SystemSettingsModel, _ROW_ID)
        if model is None:
            return SystemSettings()
        return SystemSettings(
            organization_name=model.organization_name,
            timezone=model.timezone,
            distance_unit=DistanceUnit(model.distance_unit),
            default_language=Language(model.default_language),
            telegram_enabled=model.telegram_enabled,
        )

    async def save(self, settings: SystemSettings) -> None:
        model = await self._session.get(SystemSettingsModel, _ROW_ID)
        if model is None:
            model = SystemSettingsModel(id=_ROW_ID)
            self._session.add(model)
        model.organization_name = settings.organization_name
        model.timezone = settings.timezone
        model.distance_unit = settings.distance_unit.value
        model.default_language = settings.default_language.value
        model.telegram_enabled = settings.telegram_enabled
        model.updated_at = datetime.now(UTC)
        await self._session.flush()


class TelegramSwitchProvider:
    """NotificationSettingsProvider: lee el interruptor global de Telegram."""

    def __init__(self, repository: PostgresSystemSettingsRepository) -> None:
        self._repository = repository

    async def telegram_enabled(self) -> bool:
        return (await self._repository.get()).telegram_enabled


class TripsMonitoringDefaultsGateway:
    """MonitoringDefaultsGateway: delega en la capa de aplicación de viajes."""

    def __init__(self, getter: GetMonitoringDefaultsUseCase, updater: UpdateMonitoringDefaultsUseCase) -> None:
        self._getter = getter
        self._updater = updater

    async def get(self) -> dict[str, float | int]:
        return (await self._getter.execute()).as_dict()

    async def update(self, values: dict[str, float | int], *, actor_id: uuid.UUID) -> dict[str, float | int]:
        return (await self._updater.execute(values, actor_id=actor_id)).as_dict()
