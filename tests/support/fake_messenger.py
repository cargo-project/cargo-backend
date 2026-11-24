"""Telegram simulado para los tests (UserMessenger)."""

from __future__ import annotations

import re

from app.modules.identity.application.ports.user_messenger import MessageNotDeliveredError


class FakeMessenger:
    """Telegram simulado: guarda los mensajes y puede fallar para ciertos chats."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.unreachable: set[str] = set()

    @property
    def is_configured(self) -> bool:
        return True

    async def send(self, chat_id: str, html_text: str) -> None:
        if chat_id in self.unreachable:
            raise MessageNotDeliveredError("Forbidden: bot can't initiate conversation with a user")
        self.sent.append((chat_id, html_text))

    def last_code(self) -> str:
        match = re.search(r"<b>(\d{6})</b>", self.sent[-1][1])
        assert match, self.sent[-1][1]
        return match.group(1)
