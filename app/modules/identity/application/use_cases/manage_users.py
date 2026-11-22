"""Casos de uso para administrar usuarios (solo ADMIN, se controla en presentación)."""

from __future__ import annotations

import uuid

from app.modules.identity.application.dto.identity_dto import (
    CreateUserCommand,
    UpdateUserCommand,
    UserDTO,
)
from app.modules.identity.application.ports.password_hasher import PasswordHasher
from app.modules.identity.domain.entities.user import User
from app.modules.identity.domain.exceptions.identity_errors import (
    EmailAlreadyRegisteredError,
    UserNotFoundError,
)
from app.modules.identity.domain.repositories.user_repository import UserRepository
from app.modules.identity.domain.services.password_policy import PasswordPolicy
from app.modules.identity.domain.value_objects.email import Email
from app.modules.identity.domain.value_objects.role import Role
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


class GetCurrentUserUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, user_id: uuid.UUID) -> UserDTO:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("El usuario no existe.")
        return UserDTO.from_entity(user)


class ListUsersUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self) -> list[UserDTO]:
        return [UserDTO.from_entity(user) for user in await self._users.list_all()]


class CreateUserUseCase:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, command: CreateUserCommand, *, actor_id: uuid.UUID | None) -> UserDTO:
        email = Email(command.email)
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError("Ya existe un usuario con ese correo.")
        PasswordPolicy.validate(command.password, email=email.value)
        user = User.register(
            email=email,
            full_name=command.full_name,
            password_hash=self._hasher.hash(command.password),
            role=Role(command.role),
            now=self._clock.now(),
            telegram_chat_id=command.telegram_chat_id,
        )
        await self._users.add(user)
        await self._audit.record(
            action="user.created",
            entity_type="user",
            entity_id=str(user.id),
            actor_id=actor_id,
            details={"role": user.role.value},
        )
        await self._uow.commit()
        return UserDTO.from_entity(user)


class UpdateUserUseCase:
    def __init__(self, users: UserRepository, uow: UnitOfWork, audit: AuditLog) -> None:
        self._users = users
        self._uow = uow
        self._audit = audit

    async def execute(self, command: UpdateUserCommand, *, actor_id: uuid.UUID | None) -> UserDTO:
        user = await self._users.get_by_id(command.user_id)
        if user is None:
            raise UserNotFoundError("El usuario no existe.")
        user.update_profile(
            full_name=command.full_name,
            role=Role(command.role) if command.role else None,
            is_active=command.is_active,
            telegram_chat_id=command.telegram_chat_id,
        )
        await self._users.save(user)
        await self._audit.record(action="user.updated", entity_type="user", entity_id=str(user.id), actor_id=actor_id)
        await self._uow.commit()
        return UserDTO.from_entity(user)
