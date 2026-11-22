from __future__ import annotations

import uuid

from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.domain.entities.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
)
from app.modules.notifications.domain.entities.notification_recipient import NotificationRecipient
from app.modules.notifications.infrastructure.persistence.notification_models import (
    NotificationModel,
    NotificationRecipientModel,
)


def _recipient(m: NotificationRecipientModel) -> NotificationRecipient:
    return NotificationRecipient(
        id=m.id,
        name=m.name,
        telegram_chat_id=m.telegram_chat_id,
        is_active=m.is_active,
        created_at=m.created_at,
        deleted_at=m.deleted_at,
    )


class PostgresRecipientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, recipient_id: uuid.UUID) -> NotificationRecipient | None:
        model = await self._session.get(NotificationRecipientModel, recipient_id)
        return _recipient(model) if model else None

    async def list_visible(self) -> list[NotificationRecipient]:
        rows = await self._session.scalars(
            select(NotificationRecipientModel)
            .where(NotificationRecipientModel.deleted_at.is_(None))
            .order_by(NotificationRecipientModel.name)
        )
        return [_recipient(row) for row in rows]

    async def exists_with_chat_id(self, chat_id: str) -> bool:
        condition = (NotificationRecipientModel.telegram_chat_id == chat_id) & (
            NotificationRecipientModel.deleted_at.is_(None)
        )
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def recipients_of_trip(self, trip_id: uuid.UUID) -> list[NotificationRecipient]:
        # Tabla de asociación que es de viajes; se lee con SQL para no importar su ORM.
        ids = await self._session.scalars(
            text("SELECT recipient_id FROM trip_notification_recipients WHERE trip_id = :trip_id"),
            {"trip_id": trip_id},
        )
        id_list = list(ids)
        if not id_list:
            return []
        rows = await self._session.scalars(
            select(NotificationRecipientModel).where(NotificationRecipientModel.id.in_(id_list))
        )
        return [_recipient(row) for row in rows]

    async def add(self, recipient: NotificationRecipient) -> None:
        self._session.add(
            NotificationRecipientModel(
                id=recipient.id,
                name=recipient.name,
                telegram_chat_id=recipient.telegram_chat_id,
                is_active=recipient.is_active,
                created_at=recipient.created_at,
                deleted_at=recipient.deleted_at,
            )
        )
        await self._session.flush()

    async def save(self, recipient: NotificationRecipient) -> None:
        model = await self._session.get(NotificationRecipientModel, recipient.id)
        if model is None:
            await self.add(recipient)
            return
        model.name, model.telegram_chat_id = recipient.name, recipient.telegram_chat_id
        model.is_active, model.deleted_at = recipient.is_active, recipient.deleted_at
        await self._session.flush()


def _notification(m: NotificationModel) -> Notification:
    return Notification(
        id=m.id,
        monitoring_event_id=m.monitoring_event_id,
        recipient_id=m.recipient_id,
        channel=NotificationChannel(m.channel),
        destination=m.destination,
        message=m.message,
        status=NotificationStatus(m.status),
        created_at=m.created_at,
        attempts=m.attempts,
        attempted_at=m.attempted_at,
        sent_at=m.sent_at,
        error=m.error,
    )


class PostgresNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, monitoring_event_id: uuid.UUID, recipient_id: uuid.UUID) -> Notification | None:
        model = await self._session.scalar(
            select(NotificationModel).where(
                NotificationModel.monitoring_event_id == monitoring_event_id,
                NotificationModel.recipient_id == recipient_id,
            )
        )
        return _notification(model) if model else None

    async def list_for_event(self, monitoring_event_id: uuid.UUID) -> list[Notification]:
        rows = await self._session.scalars(
            select(NotificationModel).where(NotificationModel.monitoring_event_id == monitoring_event_id)
        )
        return [_notification(row) for row in rows]

    async def add(self, notification: Notification) -> None:
        model = NotificationModel(id=notification.id)
        self._copy(notification, model)
        self._session.add(model)
        await self._session.flush()

    async def save(self, notification: Notification) -> None:
        model = await self._session.get(NotificationModel, notification.id)
        if model is None:
            await self.add(notification)
            return
        self._copy(notification, model)
        await self._session.flush()

    @staticmethod
    def _copy(n: Notification, m: NotificationModel) -> None:
        m.monitoring_event_id, m.recipient_id, m.channel = n.monitoring_event_id, n.recipient_id, n.channel.value
        m.destination, m.message, m.status = n.destination, n.message, n.status.value
        m.attempts, m.created_at, m.attempted_at = n.attempts, n.created_at, n.attempted_at
        m.sent_at, m.error = n.sent_at, n.error
