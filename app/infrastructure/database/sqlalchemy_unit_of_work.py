"""UnitOfWork implementado con SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.messaging.outbox_signal import OUTBOX_DIRTY_KEY, OutboxSignal


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession, outbox_signal: OutboxSignal | None = None) -> None:
        self._session = session
        self._outbox_signal = outbox_signal

    async def commit(self) -> None:
        await self._session.commit()
        if self._session.info.pop(OUTBOX_DIRTY_KEY, False) and self._outbox_signal is not None:
            # Despertamos al relay al toque en vez de esperar su intervalo de polling.
            self._outbox_signal.notify()

    async def rollback(self) -> None:
        self._session.info.pop(OUTBOX_DIRTY_KEY, None)
        await self._session.rollback()
