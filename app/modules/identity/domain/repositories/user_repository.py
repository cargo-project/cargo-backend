from __future__ import annotations

import uuid
from typing import Protocol

from app.modules.identity.domain.entities.user import User
from app.modules.identity.domain.value_objects.email import Email


class UserRepository(Protocol):
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...

    async def get_by_email(self, email: Email) -> User | None: ...

    async def list_all(self) -> list[User]: ...

    async def add(self, user: User) -> None: ...

    async def save(self, user: User) -> None: ...
