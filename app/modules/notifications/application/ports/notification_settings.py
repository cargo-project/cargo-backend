from __future__ import annotations

from typing import Protocol


class NotificationSettingsProvider(Protocol):
    """Interruptor global que maneja Configuración (Configuración -> Telegram)."""

    async def telegram_enabled(self) -> bool: ...
