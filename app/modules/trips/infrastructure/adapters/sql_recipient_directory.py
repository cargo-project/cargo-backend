from __future__ import annotations

import uuid

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession

_ACTIVE_RECIPIENTS = text(
    "SELECT id FROM notification_recipients WHERE id = ANY(:ids) AND is_active AND deleted_at IS NULL"
).bindparams(bindparam("ids", type_=ARRAY(UUID(as_uuid=True))))


class SqlRecipientDirectory:
    """Consulta de solo lectura a los destinatarios del contexto de notificaciones."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_missing_or_inactive(self, recipient_ids: frozenset[uuid.UUID]) -> set[uuid.UUID]:
        if not recipient_ids:
            return set()
        found = await self._session.scalars(_ACTIVE_RECIPIENTS, {"ids": list(recipient_ids)})
        return set(recipient_ids) - set(found)
