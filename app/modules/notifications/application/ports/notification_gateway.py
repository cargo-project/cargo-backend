from __future__ import annotations

from typing import Protocol


class NotificationGateway(Protocol):
    """Canal de salida (Bot API de Telegram en producción).

    Las implementaciones lanzan NotificationDeliveryError con retryable según el fallo
    (timeouts, 429 y 5xx se reintentan; 400 y 403 no).
    """

    @property
    def is_configured(self) -> bool: ...

    async def send(self, destination: str, message: str) -> None: ...
