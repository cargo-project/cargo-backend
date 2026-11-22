from __future__ import annotations

import uuid

from app.modules.notifications.domain.entities.notification_recipient import NotificationRecipient
from app.modules.notifications.domain.exceptions.notification_errors import (
    DuplicateRecipientError,
    RecipientNotFoundError,
)
from app.modules.notifications.domain.repositories.notification_repositories import RecipientRepository
from app.shared.application.audit_log import AuditLog
from app.shared.application.clock import Clock
from app.shared.application.unit_of_work import UnitOfWork


class ListRecipientsUseCase:
    def __init__(self, recipients: RecipientRepository) -> None:
        self._recipients = recipients

    async def execute(self) -> list[NotificationRecipient]:
        return await self._recipients.list_visible()


class CreateRecipientUseCase:
    def __init__(self, recipients: RecipientRepository, uow: UnitOfWork, clock: Clock, audit: AuditLog) -> None:
        self._recipients = recipients
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, *, name: str, telegram_chat_id: str, actor_id: uuid.UUID) -> NotificationRecipient:
        recipient = NotificationRecipient.register(name=name, telegram_chat_id=telegram_chat_id, now=self._clock.now())
        if await self._recipients.exists_with_chat_id(recipient.telegram_chat_id):
            raise DuplicateRecipientError("Ya existe un destinatario con ese chat ID de Telegram.")
        await self._recipients.add(recipient)
        await self._audit.record(
            action="recipient.created",
            entity_type="recipient",
            entity_id=str(recipient.id),
            actor_id=actor_id,
        )
        await self._uow.commit()
        return recipient


class DeleteRecipientUseCase:
    """Borrado lógico: así se mantiene el historial de notificaciones pasadas."""

    def __init__(self, recipients: RecipientRepository, uow: UnitOfWork, clock: Clock, audit: AuditLog) -> None:
        self._recipients = recipients
        self._uow = uow
        self._clock = clock
        self._audit = audit

    async def execute(self, recipient_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        recipient = await self._recipients.get_by_id(recipient_id)
        if recipient is None or recipient.deleted_at is not None:
            raise RecipientNotFoundError("El destinatario no existe.")
        recipient.remove(self._clock.now())
        await self._recipients.save(recipient)
        await self._audit.record(
            action="recipient.removed",
            entity_type="recipient",
            entity_id=str(recipient.id),
            actor_id=actor_id,
        )
        await self._uow.commit()
