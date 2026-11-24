from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.modules.identity.application.auth_errors import AccountPendingApprovalError, InvalidCredentialsError
from app.modules.identity.application.dto.identity_dto import (
    AuthenticatedSession,
    LoginCommand,
    UserDTO,
)
from app.modules.identity.application.ports.password_hasher import PasswordHasher
from app.modules.identity.application.ports.token_provider import TokenProvider
from app.modules.identity.domain.entities.refresh_session import RefreshSession
from app.modules.identity.domain.entities.user import User
from app.modules.identity.domain.exceptions.identity_errors import InvalidEmailError
from app.modules.identity.domain.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from app.modules.identity.domain.repositories.user_repository import UserRepository
from app.modules.identity.domain.value_objects.email import Email
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class LoginPolicy:
    max_failed_attempts: int
    lockout: timedelta
    refresh_ttl: timedelta


class AuthenticateUserUseCase:
    """Valida credenciales, aplica el bloqueo por intentos y abre una sesión de refresh."""

    def __init__(
        self,
        users: UserRepository,
        sessions: RefreshSessionRepository,
        hasher: PasswordHasher,
        tokens: TokenProvider,
        uow: UnitOfWork,
        clock: Clock,
        audit: AuditLog,
        policy: LoginPolicy,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._tokens = tokens
        self._uow = uow
        self._clock = clock
        self._audit = audit
        self._policy = policy

    async def execute(self, command: LoginCommand) -> AuthenticatedSession:
        now = self._clock.now()
        user = await self._find_user(command.email)
        if user is not None and not user.is_active and not user.is_locked(now):
            if self._hasher.verify(user.password_hash, command.password):
                raise AccountPendingApprovalError()
            raise InvalidCredentialsError()
        if user is None or not user.can_authenticate(now):
            # Mismo costo que un chequeo real, así el tiempo de respuesta no delata el estado de la cuenta.
            self._hasher.verify_against_dummy(command.password)
            raise InvalidCredentialsError()
        if not self._hasher.verify(user.password_hash, command.password):
            user.record_failed_login(now, max_attempts=self._policy.max_failed_attempts, lockout=self._policy.lockout)
            await self._users.save(user)
            await self._audit.record(
                action="user.login_failed", entity_type="user", entity_id=str(user.id), actor_id=None
            )
            await self._uow.commit()
            raise InvalidCredentialsError()

        if self._hasher.needs_rehash(user.password_hash):
            user.change_password_hash(self._hasher.hash(command.password))
        user.record_successful_login()
        await self._users.save(user)
        session = await self._open_session(user)
        await self._audit.record(action="user.login", entity_type="user", entity_id=str(user.id), actor_id=user.id)
        await self._uow.commit()
        return session

    async def _find_user(self, raw_email: str) -> User | None:
        try:
            email = Email(raw_email)
        except InvalidEmailError:
            return None
        return await self._users.get_by_email(email)

    async def _open_session(self, user: User) -> AuthenticatedSession:
        now = self._clock.now()
        refresh_token = self._tokens.new_refresh_token()
        refresh = RefreshSession.open(
            user_id=user.id,
            token_hash=self._tokens.hash_refresh_token(refresh_token),
            now=now,
            ttl=self._policy.refresh_ttl,
        )
        await self._sessions.add(refresh)
        access = self._tokens.issue_access_token(user_id=user.id, role=user.role.value, now=now)
        return AuthenticatedSession(
            user=UserDTO.from_entity(user),
            access_token=access.value,
            access_expires_at=access.expires_at,
            refresh_token=refresh_token,
            refresh_expires_at=refresh.expires_at,
        )
