from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class PasswordResetCode:
    """Código de un solo uso para restablecer la contraseña. Solo se guarda su hash, nunca el código."""

    id: uuid.UUID
    user_id: uuid.UUID
    code_hash: str
    created_at: datetime
    expires_at: datetime
    attempts: int = 0
    used_at: datetime | None = None

    @classmethod
    def issue(cls, *, user_id: uuid.UUID, code_hash: str, now: datetime, ttl: timedelta) -> PasswordResetCode:
        return cls(id=uuid.uuid4(), user_id=user_id, code_hash=code_hash, created_at=now, expires_at=now + ttl)

    def is_usable(self, now: datetime, *, max_attempts: int) -> bool:
        return self.used_at is None and now < self.expires_at and self.attempts < max_attempts

    def register_failed_attempt(self) -> None:
        self.attempts += 1

    def consume(self, now: datetime) -> None:
        self.used_at = now
