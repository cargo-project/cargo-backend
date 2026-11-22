from __future__ import annotations

import uuid

from pydantic import Field

from app.core.http.envelope import CamelModel
from app.modules.notifications.domain.entities.notification_recipient import NotificationRecipient


class RecipientRequest(CamelModel):
    name: str = Field(min_length=2, max_length=120)
    telegram_chat_id: str = Field(pattern=r"^-?\d{1,20}$")
    active: bool = True


class RecipientResponse(CamelModel):
    """Igual a ApiRecipient del frontend."""

    id: uuid.UUID
    name: str
    telegram_chat_id: str
    active: bool

    @classmethod
    def from_entity(cls, recipient: NotificationRecipient) -> RecipientResponse:
        return cls(
            id=recipient.id,
            name=recipient.name,
            telegram_chat_id=recipient.telegram_chat_id,
            active=recipient.can_receive,
        )
