"""Recuperar la contraseña con un código de un solo uso enviado al Telegram de la cuenta.

1. RequestPasswordResetUseCase: la persona escribe su correo; si la cuenta existe, está activa y tiene
   Telegram, el bot le envía un código de 6 dígitos (vence en 10 min). La respuesta es SIEMPRE la misma,
   para no revelar qué correos están registrados.
2. ConfirmPasswordResetUseCase: correo + código + nueva contraseña. Máximo 5 intentos por código; al
   cambiarla se cierran todas las sesiones y se desbloquea la cuenta.
"""

from __future__ import annotations

import html
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from app.modules.identity.application.ports.password_hasher import PasswordHasher
from app.modules.identity.application.ports.user_messenger import MessageNotDeliveredError, UserMessenger
from app.modules.identity.domain.entities.password_reset import PasswordResetCode
from app.modules.identity.domain.entities.user import User
from app.modules.identity.domain.exceptions.identity_errors import InvalidEmailError, InvalidResetCodeError
from app.modules.identity.domain.repositories.password_reset_repository import PasswordResetRepository
from app.modules.identity.domain.repositories.refresh_session_repository import RefreshSessionRepository
from app.modules.identity.domain.repositories.user_repository import UserRepository
from app.modules.identity.domain.services.password_policy import PasswordPolicy
from app.modules.identity.domain.value_objects.email import Email
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork

logger = logging.getLogger("cargo.identity")

INVALID_CODE_MESSAGE = "El código es incorrecto o ya venció. Pide uno nuevo."


@dataclass(frozen=True, slots=True)
class PasswordResetPolicy:
    code_ttl: timedelta = timedelta(minutes=10)
    max_attempts: int = 5
    max_requests: int = 3
    request_window: timedelta = timedelta(minutes=15)


async def _find_user(users: UserRepository, raw_email: str) -> User | None:
    try:
        return await users.get_by_email(Email(raw_email))
    except InvalidEmailError:
        return None


class RequestPasswordResetUseCase:
    def __init__(
        self,
        users: UserRepository,
        resets: PasswordResetRepository,
        hasher: PasswordHasher,
        messenger: UserMessenger,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
        policy: PasswordResetPolicy | None = None,
    ) -> None:
        self._users = users
        self._resets = resets
        self._hasher = hasher
        self._messenger = messenger
        self._uow = uow
        self._clock = clock
        self._audit = audit
        self._policy = policy or PasswordResetPolicy()

    async def execute(self, *, email: str) -> None:
        """Nunca indica si el correo existe: los casos sin envío solo quedan en el log."""
        user = await _find_user(self._users, email)
        if user is None or not user.is_active or not user.telegram_chat_id:
            logger.info("password reset not sent", extra={"reason": "no eligible account"})
            return
        now = self._clock.now()
        if (
            await self._resets.count_issued_since(user.id, now - self._policy.request_window)
            >= self._policy.max_requests
        ):
            logger.warning("password reset rate limited", extra={"user_id": str(user.id)})
            return
        code = f"{secrets.randbelow(1_000_000):06d}"
        await self._resets.invalidate_open_for_user(user.id, now)
        await self._resets.add(
            PasswordResetCode.issue(
                user_id=user.id, code_hash=self._hasher.hash(code), now=now, ttl=self._policy.code_ttl
            )
        )
        minutes = int(self._policy.code_ttl.total_seconds() // 60)
        try:
            await self._messenger.send(
                user.telegram_chat_id,
                "🔐 <b>CarGO · Recuperar contraseña</b>\n\n"
                f"Tu código es: <b>{code}</b>\n"
                f"Vence en {minutes} minutos y sirve una sola vez.\n\n"
                "Si no lo pediste, ignora este mensaje: tu contraseña no cambia.",
            )
        except MessageNotDeliveredError:
            # Sin envío no se guarda el código (no se hace commit); la respuesta sigue siendo la misma.
            logger.warning("password reset code not delivered", extra={"user_id": str(user.id)})
            return
        await self._audit.record(
            action="user.password_reset_requested", entity_type="user", entity_id=str(user.id), actor_id=None
        )
        await self._uow.commit()


class ConfirmPasswordResetUseCase:
    def __init__(
        self,
        users: UserRepository,
        resets: PasswordResetRepository,
        sessions: RefreshSessionRepository,
        hasher: PasswordHasher,
        messenger: UserMessenger,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
        policy: PasswordResetPolicy | None = None,
    ) -> None:
        self._users = users
        self._resets = resets
        self._sessions = sessions
        self._hasher = hasher
        self._messenger = messenger
        self._uow = uow
        self._clock = clock
        self._audit = audit
        self._policy = policy or PasswordResetPolicy()

    async def execute(self, *, email: str, code: str, new_password: str) -> None:
        now = self._clock.now()
        user = await _find_user(self._users, email)
        record = await self._resets.latest_for_user(user.id) if user is not None else None
        if user is None or record is None or not record.is_usable(now, max_attempts=self._policy.max_attempts):
            raise InvalidResetCodeError(INVALID_CODE_MESSAGE)
        if not self._hasher.verify(record.code_hash, code.strip()):
            record.register_failed_attempt()
            await self._resets.save(record)
            await self._uow.commit()
            raise InvalidResetCodeError(INVALID_CODE_MESSAGE)
        # Si la contraseña nueva no cumple la política, el código sigue sirviendo para otro intento.
        PasswordPolicy.validate(new_password, email=user.email.value)
        user.change_password_hash(self._hasher.hash(new_password))
        user.record_successful_login()  # desbloquea la cuenta si estaba bloqueada por intentos fallidos
        record.consume(now)
        await self._users.save(user)
        await self._resets.save(record)
        await self._sessions.revoke_all_for_user(user.id, now)
        await self._audit.record(
            action="user.password_reset", entity_type="user", entity_id=str(user.id), actor_id=None
        )
        await self._uow.commit()
        if user.telegram_chat_id:
            try:
                await self._messenger.send(
                    user.telegram_chat_id,
                    f"✅ <b>CarGO</b>\n\nHola {html.escape(user.full_name)}, tu contraseña se cambió correctamente "
                    "y se cerraron tus sesiones abiertas. Si no fuiste tú, avisa al administrador.",
                )
            except MessageNotDeliveredError:
                logger.warning("password reset confirmation not delivered", extra={"user_id": str(user.id)})
