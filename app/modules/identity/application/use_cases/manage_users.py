"""Casos de uso para administrar usuarios (solo ADMIN, se controla en presentación)."""

from __future__ import annotations

import contextlib
import html
import re
import uuid

from app.modules.identity.application.dto.identity_dto import (
    CreateUserCommand,
    UpdateUserCommand,
    UserDTO,
)
from app.modules.identity.application.ports.password_hasher import PasswordHasher
from app.modules.identity.application.ports.user_messenger import MessageNotDeliveredError, UserMessenger
from app.modules.identity.domain.entities.user import User
from app.modules.identity.domain.exceptions.identity_errors import (
    EmailAlreadyRegisteredError,
    SelfLockoutError,
    TelegramRequiredError,
    TelegramUnreachableError,
    UserNotFoundError,
)
from app.modules.identity.domain.repositories.user_repository import UserRepository
from app.modules.identity.domain.services.password_policy import PasswordPolicy
from app.modules.identity.domain.value_objects.email import Email
from app.modules.identity.domain.value_objects.role import Role
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork

_CHAT_ID = re.compile(r"^-?\d{1,20}$")


def _required_chat_id(raw: str | None) -> str:
    chat_id = (raw or "").strip()
    if not _CHAT_ID.match(chat_id):
        raise TelegramRequiredError(
            "El chat ID de Telegram es obligatorio (solo números): ahí llegan los códigos para recuperar la contraseña."
        )
    return chat_id


def _linked_message(full_name: str) -> str:
    return (
        f"👋 Hola {html.escape(full_name)}, tu cuenta de <b>CarGO</b> quedó vinculada a este chat.\n"
        "Aquí te llegarán los códigos para recuperar tu contraseña."
    )


async def _verify_chat(
    messenger: UserMessenger | None, chat_id: str, full_name: str, message: str | None = None
) -> None:
    """El bot saluda al chat; si no puede escribirle, la cuenta quedaría sin forma de recuperar la contraseña."""
    if messenger is None or not messenger.is_configured:
        return
    try:
        await messenger.send(chat_id, message or _linked_message(full_name))
    except MessageNotDeliveredError as error:
        raise TelegramUnreachableError(
            "El bot de CarGO no pudo escribir a ese chat de Telegram. Revisa el chat ID y pide a la persona que "
            "abra el bot y presione «Iniciar» antes de guardar."
        ) from error


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
        messenger: UserMessenger | None = None,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._uow = uow
        self._clock = clock
        self._audit = audit
        self._messenger = messenger

    async def execute(self, command: CreateUserCommand, *, actor_id: uuid.UUID | None) -> UserDTO:
        email = Email(command.email)
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError("Ya existe un usuario con ese correo.")
        PasswordPolicy.validate(command.password, email=email.value)
        chat_id = _required_chat_id(command.telegram_chat_id)
        if command.verify_telegram:
            await _verify_chat(self._messenger, chat_id, command.full_name)
        user = User.register(
            email=email,
            full_name=command.full_name,
            password_hash=self._hasher.hash(command.password),
            role=Role(command.role),
            now=self._clock.now(),
            telegram_chat_id=chat_id,
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
    def __init__(
        self, users: UserRepository, uow: UnitOfWork, audit: AuditLog, messenger: UserMessenger | None = None
    ) -> None:
        self._users = users
        self._uow = uow
        self._audit = audit
        self._messenger = messenger

    async def execute(self, command: UpdateUserCommand, *, actor_id: uuid.UUID | None) -> UserDTO:
        user = await self._users.get_by_id(command.user_id)
        if user is None:
            raise UserNotFoundError("El usuario no existe.")
        demoting = command.role is not None and Role(command.role) != Role.ADMIN
        if actor_id == user.id and (demoting or command.is_active is False):
            raise SelfLockoutError("No puedes quitarte el rol de administrador ni desactivar tu propia cuenta.")
        if command.telegram_chat_id is not None:
            chat_id = _required_chat_id(command.telegram_chat_id)  # no se puede dejar una cuenta sin Telegram
            if chat_id != user.telegram_chat_id:
                await _verify_chat(self._messenger, chat_id, command.full_name or user.full_name)
        activated = command.is_active is True and not user.is_active
        user.update_profile(
            full_name=command.full_name,
            role=Role(command.role) if command.role else None,
            is_active=command.is_active,
            telegram_chat_id=command.telegram_chat_id,
        )
        await self._users.save(user)
        await self._audit.record(action="user.updated", entity_type="user", entity_id=str(user.id), actor_id=actor_id)
        await self._uow.commit()
        if activated and user.telegram_chat_id and self._messenger is not None and self._messenger.is_configured:
            with contextlib.suppress(MessageNotDeliveredError):  # aviso de cortesía: la cuenta igual queda activa
                await self._messenger.send(
                    user.telegram_chat_id,
                    f"✅ Hola {html.escape(user.full_name)}, tu cuenta de <b>CarGO</b> ya está activa. "
                    "Ya puedes iniciar sesión.",
                )
        return UserDTO.from_entity(user)


class RegisterAccountUseCase:
    """Alta desde la pantalla de login: queda como Operador desactivado hasta que un administrador la apruebe."""

    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
        messenger: UserMessenger | None = None,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._uow = uow
        self._clock = clock
        self._audit = audit
        self._messenger = messenger

    async def execute(self, *, email: str, full_name: str, password: str, telegram_chat_id: str) -> UserDTO:
        address = Email(email)
        if await self._users.get_by_email(address) is not None:
            raise EmailAlreadyRegisteredError("Ya existe una cuenta con ese correo.")
        PasswordPolicy.validate(password, email=address.value)
        chat_id = _required_chat_id(telegram_chat_id)
        user = User.register(
            email=address,
            full_name=full_name,
            password_hash=self._hasher.hash(password),
            role=Role.OPERATOR,
            now=self._clock.now(),
            telegram_chat_id=chat_id,
            is_active=False,
        )
        await _verify_chat(
            self._messenger,
            chat_id,
            user.full_name,
            f"👋 Hola {html.escape(user.full_name)}, recibimos tu solicitud de cuenta en <b>CarGO</b>.\n"
            "Un administrador debe aprobarla; te avisaremos por aquí cuando puedas ingresar.",
        )
        await self._users.add(user)
        await self._audit.record(
            action="user.registered",
            entity_type="user",
            entity_id=str(user.id),
            actor_id=None,
            details={"role": user.role.value, "status": "pending_approval"},
        )
        await self._uow.commit()
        return UserDTO.from_entity(user)
