"""Scope por request o por mensaje: una sesión de BD y una transacción."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.resources import AppResources
from app.infrastructure.database.postgres_audit_log import PostgresAuditLog
from app.infrastructure.database.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.messaging.outbox_event_publisher import OutboxEventPublisher


@dataclass
class Scope:
    resources: AppResources
    session: AsyncSession
    uow: SqlAlchemyUnitOfWork = field(init=False)
    publisher: OutboxEventPublisher = field(init=False)
    audit: PostgresAuditLog = field(init=False)

    def __post_init__(self) -> None:
        self.uow = SqlAlchemyUnitOfWork(self.session, self.resources.outbox_signal)
        self.publisher = OutboxEventPublisher(self.session, self.resources.clock)
        self.audit = PostgresAuditLog(self.session, self.resources.clock)


@asynccontextmanager
async def open_scope(resources: AppResources) -> AsyncIterator[Scope]:
    async with resources.session_factory() as session:
        try:
            yield Scope(resources=resources, session=session)
        finally:
            if session.in_transaction():
                await session.rollback()
