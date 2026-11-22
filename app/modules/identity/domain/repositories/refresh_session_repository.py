from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from app.modules.identity.domain.entities.refresh_session import RefreshSession


class RefreshSessionRepository(Protocol):
    async def get_by_token_hash(self, token_hash: str) -> RefreshSession | None: ...

    async def add(self, session: RefreshSession) -> None: ...

    async def save(self, session: RefreshSession) -> None: ...

    async def revoke_family(self, family_id: uuid.UUID, now: datetime) -> None: ...

    async def revoke_all_for_user(self, user_id: uuid.UUID, now: datetime) -> None: ...
