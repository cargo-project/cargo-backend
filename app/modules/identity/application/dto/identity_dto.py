from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.modules.identity.domain.entities.user import User


@dataclass(frozen=True, slots=True)
class UserDTO:
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    telegram_chat_id: str | None

    @classmethod
    def from_entity(cls, user: User) -> UserDTO:
        return cls(
            id=user.id,
            email=user.email.value,
            full_name=user.full_name,
            role=user.role.value,
            is_active=user.is_active,
            telegram_chat_id=user.telegram_chat_id,
        )


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    user: UserDTO
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class LoginCommand:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class CreateUserCommand:
    email: str
    full_name: str
    password: str
    role: str
    telegram_chat_id: str | None = None
    # El bot le escribe al chat para comprobar que existe (los scripts de datos de prueba lo desactivan).
    verify_telegram: bool = True


@dataclass(frozen=True, slots=True)
class UpdateUserCommand:
    user_id: uuid.UUID
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    telegram_chat_id: str | None = None
