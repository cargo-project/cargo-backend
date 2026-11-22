from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.shared.domain.errors import BusinessRuleViolationError


class InvalidSettingsError(BusinessRuleViolationError):
    code = "invalid_settings"


class DistanceUnit(StrEnum):
    KILOMETERS = "km"
    MILES = "mi"


class Language(StrEnum):
    SPANISH = "es"
    ENGLISH = "en"


@dataclass(frozen=True, slots=True)
class SystemSettings:
    """Preferencias de toda la organización. Hay una sola (agregado de una fila)."""

    organization_name: str = "CarGO"
    timezone: str = "America/Lima"
    distance_unit: DistanceUnit = DistanceUnit.KILOMETERS
    default_language: Language = Language.SPANISH
    telegram_enabled: bool = True

    def __post_init__(self) -> None:
        name = " ".join(self.organization_name.split())
        if not 2 <= len(name) <= 120:
            raise InvalidSettingsError("El nombre de la organización debe tener entre 2 y 120 caracteres.")
        object.__setattr__(self, "organization_name", name)
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise InvalidSettingsError(f"Zona horaria desconocida: {self.timezone}") from error


class SystemSettingsRepository(Protocol):
    async def get(self) -> SystemSettings: ...

    async def save(self, settings: SystemSettings) -> None: ...
