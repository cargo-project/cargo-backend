from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from app.core.http.envelope import CamelModel
from app.modules.identity.application.dto.identity_dto import UserDTO


class LoginRequest(CamelModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class UserResponse(CamelModel):
    """Igual a ApiUser del frontend."""

    id: uuid.UUID
    email: str
    full_name: str
    role: Literal["ADMIN", "OPERATOR"]
    telegram_chat_id: str | None = None
    is_active: bool

    @classmethod
    def from_dto(cls, dto: UserDTO) -> UserResponse:
        return cls(
            id=dto.id,
            email=dto.email,
            full_name=dto.full_name,
            role=dto.role,
            telegram_chat_id=dto.telegram_chat_id,
            is_active=dto.is_active,
        )


class CreateUserRequest(CamelModel):
    email: str = Field(max_length=254)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["ADMIN", "OPERATOR"] = "OPERATOR"
    # Obligatorio: ahí llegan los códigos para recuperar la contraseña.
    telegram_chat_id: str = Field(pattern=r"^-?\d{1,20}$")


class UpdateUserRequest(CamelModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Literal["ADMIN", "OPERATOR"] | None = None
    is_active: bool | None = None
    telegram_chat_id: str | None = Field(default=None, pattern=r"^-?\d{1,20}$")


class PasswordResetRequest(CamelModel):
    email: str = Field(min_length=3, max_length=254)


class PasswordResetConfirm(CamelModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(pattern=r"^\s*\d{6}\s*$")
    new_password: str = Field(min_length=10, max_length=128)


class RegisterRequest(CamelModel):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)
    telegram_chat_id: str = Field(pattern=r"^-?\d{1,20}$")


class UpdateProfileRequest(CamelModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    telegram_chat_id: str | None = Field(default=None, pattern=r"^-?\d{1,20}$")
