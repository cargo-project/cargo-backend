from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.audit_log_model import AuditLogModel
from app.shared.application.clock import Clock

logger = logging.getLogger("cargo.audit")


class PostgresAuditLog:
    """Guarda la auditoría dentro de la misma transacción del que llama (va junto con el cambio)."""

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    async def record(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        actor_id: uuid.UUID | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuditLogModel(
                id=uuid.uuid4(),
                occurred_at=self._clock.now(),
                actor_id=actor_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details or {},
            )
        )
        logger.info("audit", extra={"action": action, "entity": f"{entity_type}:{entity_id}"})
