from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.modules.notifications.application.dto.notification_dto import (
    DispatchSummary,
    EventNotificationRequest,
)
from app.modules.notifications.application.notification_message_composer import (
    NotificationMessageComposer,
)
from app.modules.notifications.application.ports.notification_gateway import NotificationGateway
from app.modules.notifications.application.ports.notification_settings import (
    NotificationSettingsProvider,
)
from app.modules.notifications.domain.entities.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)
from app.modules.notifications.domain.exceptions.notification_errors import NotificationDeliveryError
from app.modules.notifications.domain.repositories.notification_repositories import (
    NotificationRepository,
    RecipientRepository,
)
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork

logger = logging.getLogger("cargo.notifications")

Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 2.0

    def delay_before(self, attempt: int) -> float:
        """Backoff exponencial: 0, base, 2*base, 4*base..."""
        return 0.0 if attempt <= 1 else self.base_delay_seconds * 2 ** (attempt - 2)


class DispatchEventNotificationsUseCase:
    """Avisa del evento detectado a todos los destinatarios del viaje.

    * Idempotente por (evento, destinatario): si events/detected llega de nuevo no se
      manda dos veces (clave única en BD + chequeo de estado).
    * Cada intento queda guardado (attempts, attempted_at, sent_at, error).
    * Si falla, el MonitoringEvent no se toca; ya está guardado.
    """

    def __init__(
        self,
        recipients: RecipientRepository,
        notifications: NotificationRepository,
        gateway: NotificationGateway,
        settings: NotificationSettingsProvider,
        uow: UnitOfWork,
        clock: Clock,
        retry_policy: RetryPolicy,
        composer: NotificationMessageComposer | None = None,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self._recipients = recipients
        self._notifications = notifications
        self._gateway = gateway
        self._settings = settings
        self._uow = uow
        self._clock = clock
        self._retry = retry_policy
        self._composer = composer or NotificationMessageComposer()
        self._sleep = sleep

    async def execute(self, request: EventNotificationRequest) -> DispatchSummary:
        message = self._composer.compose(request)
        enabled = await self._settings.telegram_enabled()
        sent = failed = skipped = handled = 0
        for recipient in await self._recipients.recipients_of_trip(request.trip_id):
            notification = await self._notifications.find(request.monitoring_event_id, recipient.id)
            if notification is not None and notification.is_final:
                handled += 1
                continue
            if notification is None:
                notification = Notification.prepare(
                    monitoring_event_id=request.monitoring_event_id,
                    recipient_id=recipient.id,
                    channel=NotificationChannel.TELEGRAM,
                    destination=recipient.telegram_chat_id,
                    message=message,
                    now=self._clock.now(),
                )
                await self._notifications.add(notification)
                await self._uow.commit()

            if not recipient.can_receive:
                notification.skip(self._clock.now(), "Destinatario inactivo.")
            elif not enabled:
                notification.skip(self._clock.now(), "Notificaciones por Telegram deshabilitadas.")
            elif not self._gateway.is_configured:
                notification.skip(self._clock.now(), "Telegram no configurado (TELEGRAM_BOT_TOKEN).")
            else:
                await self._deliver(notification)
            await self._notifications.save(notification)
            await self._uow.commit()

            if notification.status == NotificationStatus.SENT:
                sent += 1
            elif notification.status == NotificationStatus.SKIPPED:
                skipped += 1
            else:
                failed += 1
        return DispatchSummary(sent=sent, failed=failed, skipped=skipped, already_handled=handled)

    async def _deliver(self, notification: Notification) -> None:
        for attempt in range(notification.attempts + 1, self._retry.max_attempts + 1):
            await self._sleep(self._retry.delay_before(attempt))
            try:
                await self._gateway.send(notification.destination, notification.message)
            except NotificationDeliveryError as error:
                final = not error.retryable or attempt >= self._retry.max_attempts
                notification.record_failure(self._clock.now(), str(error), final=final)
                logger.warning(
                    "telegram delivery failed",
                    extra={
                        "notification": str(notification.id),
                        "attempt": attempt,
                        "retryable": error.retryable,
                        "error": str(error),
                    },
                )
                if final:
                    return
                await self._notifications.save(notification)
                await self._uow.commit()
                continue
            notification.record_success(self._clock.now())
            logger.info("telegram notification sent", extra={"notification": str(notification.id)})
            return
        if notification.status == NotificationStatus.PENDING:
            notification.record_failure(self._clock.now(), "Intentos agotados.", final=True)
