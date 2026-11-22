"""EventPublisher con el patrón Transactional Outbox."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.messaging.outbox_model import IntegrationOutboxModel
from app.infrastructure.messaging.outbox_signal import OUTBOX_DIRTY_KEY
from app.shared.application.clock import Clock
from app.shared.application.event_publisher import IntegrationEvent


class OutboxEventPublisher:
    """Guarda el evento en integration_outbox dentro de la transacción actual.

    El relay solo lo ve si el cambio de negocio hace commit, así evitamos el
    problema de escribir en PostgreSQL y en MQTT por separado (dual write).
    """

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self._session = session
        self._clock = clock

    async def publish(self, event: IntegrationEvent) -> None:
        self._session.add(
            IntegrationOutboxModel(
                id=uuid.uuid4(),
                topic=event.topic,
                payload=event.payload,
                retain=event.retain,
                created_at=self._clock.now(),
                attempts=0,
            )
        )
        self._session.info[OUTBOX_DIRTY_KEY] = True
