from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.shared.domain.entity import Entity


@dataclass(eq=False)
class RefreshSession(Entity):
    """Refresh token rotativo. Solo se guarda su hash.

    Las sesiones que salen de una rotación comparten family_id. Si llega un token ya
    rotado es señal de reuso (token robado) y se revoca toda la familia.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    family_id: uuid.UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @classmethod
    def open(
        cls,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        now: datetime,
        ttl: timedelta,
        family_id: uuid.UUID | None = None,
    ) -> RefreshSession:
        return cls(
            id=uuid.uuid4(),
            user_id=user_id,
            family_id=family_id or uuid.uuid4(),
            token_hash=token_hash,
            created_at=now,
            expires_at=now + ttl,
        )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now
