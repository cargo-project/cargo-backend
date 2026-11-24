from __future__ import annotations

from typing import Protocol


class MessageNotDeliveredError(Exception):
    """El mensaje no llegó al chat (ID incorrecto, bot no iniciado por la persona o Telegram caído)."""


class UserMessenger(Protocol):
    """Mensajes directos a la persona (por ahora, Telegram)."""

    @property
    def is_configured(self) -> bool: ...

    async def send(self, chat_id: str, html_text: str) -> None:
        """Lanza MessageNotDeliveredError si el mensaje no se pudo entregar."""
        ...
