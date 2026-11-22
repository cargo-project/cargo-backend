from __future__ import annotations

import uuid

from app.modules.identity.application.auth_errors import InvalidCredentialsError
from app.modules.identity.application.ports.password_hasher import PasswordHasher
from app.modules.identity.domain.exceptions.identity_errors import UserNotFoundError
from app.modules.identity.domain.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from app.modules.identity.domain.repositories.user_repository import UserRepository
from app.modules.identity.domain.services.password_policy import PasswordPolicy
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


class ChangePasswordUseCase:
    """Cambia la contraseña y revoca todas las sesiones de refresh del usuario."""

    def __init__(
        self,
        users: UserRepository,
        sessions: RefreshSessionRepository,
        hasher: PasswordHasher,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, *, user_id: uuid.UUID, current_password: str, new_password: str) -> None:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("El usuario no existe.")
        if not self._hasher.verify(user.password_hash, current_password):
            raise InvalidCredentialsError()
        PasswordPolicy.validate(new_password, email=user.email.value)
        user.change_password_hash(self._hasher.hash(new_password))
        await self._users.save(user)
        await self._sessions.revoke_all_for_user(user.id, self._clock.now())
        await self._audit.record(
            action="user.password_changed", entity_type="user", entity_id=str(user.id), actor_id=user.id
        )
        await self._uow.commit()
