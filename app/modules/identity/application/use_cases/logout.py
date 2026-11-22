from __future__ import annotations

from app.modules.identity.application.ports.token_provider import TokenProvider
from app.modules.identity.domain.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


class LogoutUseCase:
    """Revoca la sesión de refresh que llega. Idempotente: cerrar sesión dos veces no es error."""

    def __init__(
        self, sessions: RefreshSessionRepository, tokens: TokenProvider, uow: UnitOfWork, clock: Clock
    ) -> None:
        self._sessions = sessions
        self._tokens = tokens
        self._uow = uow
        self._clock = clock

    async def execute(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        session = await self._sessions.get_by_token_hash(self._tokens.hash_refresh_token(refresh_token))
        if session is None:
            return
        session.revoke(self._clock.now())
        await self._sessions.save(session)
        await self._uow.commit()
