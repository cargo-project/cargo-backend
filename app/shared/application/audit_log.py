"""Puerto de auditoría para operaciones que tienen que quedar registradas (inicio de viaje, evento revisado...)."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class AuditLog(Protocol):
    async def record(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        actor_id: UUID | None,
        details: dict[str, Any] | None = None,
    ) -> None: ...
