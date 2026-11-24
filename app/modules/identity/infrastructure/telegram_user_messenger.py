"""UserMessenger sobre el mismo canal de Telegram que usan las alertas."""

from __future__ import annotations

from typing import Protocol

from app.modules.identity.application.ports.user_messenger import MessageNotDeliveredError


class _TelegramChannel(Protocol):
    @property
    def is_configured(self) -> bool: ...

    async def send(self, destination: str, message: str) -> None: ...


class TelegramUserMessenger:
    def __init__(self, telegram: _TelegramChannel) -> None:
        self._telegram = telegram

    @property
    def is_configured(self) -> bool:
        return self._telegram.is_configured

    async def send(self, chat_id: str, html_text: str) -> None:
        try:
            await self._telegram.send(chat_id, html_text)
        except Exception as error:  # cualquier falla de entrega (chat inválido, bot no iniciado, red)
            raise MessageNotDeliveredError(str(error)) from error
