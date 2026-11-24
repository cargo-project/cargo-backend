from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from app.modules.identity.domain.entities.password_reset import PasswordResetCode


class PasswordResetRepository(Protocol):
    async def latest_for_user(self, user_id: uuid.UUID) -> PasswordResetCode | None: ...

    async def count_issued_since(self, user_id: uuid.UUID, since: datetime) -> int: ...

    async def invalidate_open_for_user(self, user_id: uuid.UUID, now: datetime) -> None: ...

    async def add(self, code: PasswordResetCode) -> None: ...

    async def save(self, code: PasswordResetCode) -> None: ...
