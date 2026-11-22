from __future__ import annotations

import logging
from datetime import timedelta

from app.modules.identity.application.auth_errors import InvalidSessionError
from app.modules.identity.application.dto.identity_dto import AuthenticatedSession, UserDTO
from app.modules.identity.application.ports.token_provider import TokenProvider
from app.modules.identity.domain.entities.refresh_session import RefreshSession
from app.modules.identity.domain.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from app.modules.identity.domain.repositories.user_repository import UserRepository
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork

logger = logging.getLogger("cargo.identity")


class RefreshSessionUseCase:
    """Rota el refresh token y entrega un access token nuevo.

    Si alguien reusa un token ya rotado se revoca toda la familia de sesiones
    (detección de robo de token, OWASP ASVS 3.5).
    """

    def __init__(
        self,
        users: UserRepository,
        sessions: RefreshSessionRepository,
        tokens: TokenProvider,
        uow: UnitOfWork,
        clock: Clock,
        refresh_ttl: timedelta,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._tokens = tokens
        self._uow = uow
        self._clock = clock
        self._refresh_ttl = refresh_ttl

    async def execute(self, refresh_token: str | None) -> AuthenticatedSession:
        if not refresh_token:
            raise InvalidSessionError()
        now = self._clock.now()
        current = await self._sessions.get_by_token_hash(self._tokens.hash_refresh_token(refresh_token))
        if current is None:
            raise InvalidSessionError()
        if current.is_revoked:
            logger.warning(
                "refresh token reuse detected; revoking family",
                extra={"user_id": str(current.user_id), "family_id": str(current.family_id)},
            )
            await self._sessions.revoke_family(current.family_id, now)
            await self._uow.commit()
            raise InvalidSessionError()
        if current.is_expired(now):
            raise InvalidSessionError()
        user = await self._users.get_by_id(current.user_id)
        if user is None or not user.can_authenticate(now):
            raise InvalidSessionError()

        current.revoke(now)
        await self._sessions.save(current)
        new_token = self._tokens.new_refresh_token()
        rotated = RefreshSession.open(
            user_id=user.id,
            token_hash=self._tokens.hash_refresh_token(new_token),
            now=now,
            ttl=self._refresh_ttl,
            family_id=current.family_id,
        )
        await self._sessions.add(rotated)
        access = self._tokens.issue_access_token(user_id=user.id, role=user.role.value, now=now)
        await self._uow.commit()
        return AuthenticatedSession(
            user=UserDTO.from_entity(user),
            access_token=access.value,
            access_expires_at=access.expires_at,
            refresh_token=new_token,
            refresh_expires_at=rotated.expires_at,
        )


class ValidateRefreshSessionUseCase:
    """Chequeo de solo lectura que usa el handshake del WebSocket cuando venció el access token."""

    def __init__(
        self, sessions: RefreshSessionRepository, tokens: TokenProvider, users: UserRepository, clock: Clock
    ) -> None:
        self._sessions = sessions
        self._tokens = tokens
        self._users = users
        self._clock = clock

    async def execute(self, refresh_token: str | None) -> UserDTO:
        if not refresh_token:
            raise InvalidSessionError()
        now = self._clock.now()
        session = await self._sessions.get_by_token_hash(self._tokens.hash_refresh_token(refresh_token))
        if session is None or session.is_revoked or session.is_expired(now):
            raise InvalidSessionError()
        user = await self._users.get_by_id(session.user_id)
        if user is None or not user.can_authenticate(now):
            raise InvalidSessionError()
        return UserDTO.from_entity(user)
