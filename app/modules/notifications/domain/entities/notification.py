from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.modules.notifications.domain.exceptions.notification_errors import (
    InvalidNotificationTransitionError,
)
from app.shared.domain.entity import Entity


class NotificationChannel(StrEnum):
    TELEGRAM = "telegram"


class NotificationStatus(StrEnum):
    PENDING = "pending"  # creada, todavía sin intentar o esperando reintento
    SENT = "sent"
    FAILED = "failed"  # se acabaron los intentos o el error no se puede reintentar
    SKIPPED = "skipped"  # canal apagado o sin configurar


@dataclass(eq=False)
class Notification(Entity):
    """Envío de un MonitoringEvent a un destinatario por un canal.

    Tiene su propio ciclo de vida: si Telegram se cae, esta entidad pasa a FAILED pero
    el evento detectado no se toca ni se borra.
    """

    id: uuid.UUID
    monitoring_event_id: uuid.UUID
    recipient_id: uuid.UUID
    channel: NotificationChannel
    destination: str
    message: str
    status: NotificationStatus
    created_at: datetime
    attempts: int = 0
    attempted_at: datetime | None = None
    sent_at: datetime | None = None
    error: str | None = None

    @classmethod
    def prepare(
        cls,
        *,
        monitoring_event_id: uuid.UUID,
        recipient_id: uuid.UUID,
        channel: NotificationChannel,
        destination: str,
        message: str,
        now: datetime,
    ) -> Notification:
        return cls(
            id=uuid.uuid4(),
            monitoring_event_id=monitoring_event_id,
            recipient_id=recipient_id,
            channel=channel,
            destination=destination,
            message=message,
            status=NotificationStatus.PENDING,
            created_at=now,
        )

    @property
    def is_final(self) -> bool:
        return self.status in (NotificationStatus.SENT, NotificationStatus.FAILED, NotificationStatus.SKIPPED)

    def record_success(self, now: datetime) -> None:
        self._ensure_pending()
        self.attempts += 1
        self.attempted_at = now
        self.sent_at = now
        self.error = None
        self.status = NotificationStatus.SENT

    def record_failure(self, now: datetime, error: str, *, final: bool) -> None:
        self._ensure_pending()
        self.attempts += 1
        self.attempted_at = now
        self.error = error[:500]
        if final:
            self.status = NotificationStatus.FAILED

    def skip(self, now: datetime, reason: str) -> None:
        self._ensure_pending()
        self.attempted_at = now
        self.error = reason[:500]
        self.status = NotificationStatus.SKIPPED

    def _ensure_pending(self) -> None:
        if self.status != NotificationStatus.PENDING:
            raise InvalidNotificationTransitionError(f"La notificación ya está en estado {self.status.value}.")
