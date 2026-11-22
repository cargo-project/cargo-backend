from __future__ import annotations

import uuid
from typing import Protocol


class RecipientDirectory(Protocol):
    """Valida los destinatarios de notificaciones (son del contexto de notificaciones)."""

    async def find_missing_or_inactive(self, recipient_ids: frozenset[uuid.UUID]) -> set[uuid.UUID]: ...
