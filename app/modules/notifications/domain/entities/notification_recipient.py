from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.modules.notifications.domain.exceptions.notification_errors import InvalidRecipientError
from app.shared.domain.entity import Entity

_CHAT_ID = re.compile(r"^-?\d{1,20}$")


@dataclass(eq=False)
class NotificationRecipient(Entity):
    """Persona (o grupo de Telegram) que recibe alertas.

    Quitarlo es un borrado lógico: las notificaciones y viajes anteriores lo siguen
    referenciando, así no se pierde el historial.
    """

    id: uuid.UUID
    name: str
    telegram_chat_id: str
    is_active: bool
    created_at: datetime
    deleted_at: datetime | None = None

    @classmethod
    def register(cls, *, name: str, telegram_chat_id: str, now: datetime) -> NotificationRecipient:
        cleaned_name = " ".join(name.split())
        chat_id = telegram_chat_id.strip()
        if not 2 <= len(cleaned_name) <= 120:
            raise InvalidRecipientError("El nombre del destinatario debe tener entre 2 y 120 caracteres.")
        if not _CHAT_ID.match(chat_id):
            raise InvalidRecipientError("El chat ID de Telegram debe ser numérico.")
        return cls(id=uuid.uuid4(), name=cleaned_name, telegram_chat_id=chat_id, is_active=True, created_at=now)

    @property
    def can_receive(self) -> bool:
        return self.is_active and self.deleted_at is None

    def remove(self, now: datetime) -> None:
        self.is_active = False
        self.deleted_at = now
