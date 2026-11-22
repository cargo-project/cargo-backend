from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal, Protocol


class MonitoringDefaultsGateway(Protocol):
    """Acceso a los umbrales de monitoreo por defecto (son del contexto de viajes)."""

    async def get(self) -> dict[str, float | int]: ...

    async def update(self, values: dict[str, float | int], *, actor_id: uuid.UUID) -> dict[str, float | int]: ...


@dataclass(frozen=True, slots=True)
class IntegrationStatus:
    key: str
    name: str
    status: Literal["online", "offline", "unconfigured"]
    detail: str


class IntegrationProbe(Protocol):
    async def check(self) -> IntegrationStatus: ...
