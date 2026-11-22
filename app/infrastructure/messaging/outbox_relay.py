"""Pasa a MQTT las filas del outbox ya confirmadas (al menos una vez, QoS 1)."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.messaging.outbox_model import IntegrationOutboxModel
from app.infrastructure.messaging.outbox_signal import OutboxSignal

logger = logging.getLogger("cargo.outbox")


class MessagePublisher(Protocol):
    async def publish_json(self, topic: str, payload: dict[str, object], *, retain: bool) -> None: ...


class OutboxRelay:
    """Publica las filas pendientes en orden de creación y las borra cuando el broker confirma.

    Con FOR UPDATE SKIP LOCKED pueden correr varios relays a la vez sin mandar la misma
    fila dos veces en operación normal. Si el proceso se cae entre publicar y borrar,
    la fila puede salir de nuevo: por eso los consumidores son idempotentes.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: MessagePublisher,
        signal: OutboxSignal,
        *,
        batch_size: int = 200,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._signal = signal
        self._batch_size = batch_size
        self._poll_interval = poll_interval_seconds

    async def run(self, stop: asyncio.Event) -> None:
        logger.info("outbox relay started")
        while not stop.is_set():
            try:
                relayed = await self.relay_once()
            except Exception:
                logger.exception("outbox relay iteration failed")
                relayed = 0
            if relayed < self._batch_size:
                await self._signal.wait(self._poll_interval)
        logger.info("outbox relay stopped")

    async def relay_once(self) -> int:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(IntegrationOutboxModel)
                    .order_by(IntegrationOutboxModel.created_at)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            relayed = 0
            for row in rows:
                try:
                    await self._publisher.publish_json(row.topic, row.payload, retain=row.retain)
                except Exception as error:  # broker caído: dejamos la fila y reintentamos después
                    row.attempts += 1
                    row.last_error = str(error)[:500]
                    logger.warning("outbox publish failed", extra={"topic": row.topic, "error": str(error)})
                    break
                await session.delete(row)
                relayed += 1
            await session.commit()
            return relayed
