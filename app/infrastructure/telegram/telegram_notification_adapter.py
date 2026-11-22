"""NotificationGateway para la Bot API de Telegram (sendMessage)."""

from __future__ import annotations

import httpx

from app.modules.notifications.domain.exceptions.notification_errors import NotificationDeliveryError


class TelegramNotificationAdapter:
    def __init__(self, client: httpx.AsyncClient, bot_token: str | None, api_base: str) -> None:
        self._client = client
        self._bot_token = bot_token
        self._api_base = api_base.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self._bot_token)

    async def send(self, destination: str, message: str) -> None:
        if not self._bot_token:
            raise NotificationDeliveryError("Telegram no está configurado.", retryable=False)
        url = f"{self._api_base}/bot{self._bot_token}/sendMessage"
        try:
            # parse_mode HTML: el compositor arma negritas y el link de Google Maps, con los
            # valores dinámicos ya escapados.
            response = await self._client.post(
                url,
                json={
                    "chat_id": destination,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        except httpx.TimeoutException as error:
            raise NotificationDeliveryError("Tiempo de espera agotado con Telegram.", retryable=True) from error
        except httpx.HTTPError as error:
            # Nunca loguear la URL: lleva el token del bot.
            raise NotificationDeliveryError(
                f"Error de red con Telegram ({type(error).__name__}).", retryable=True
            ) from error

        if response.status_code == 200:
            return
        description = ""
        try:
            description = str(response.json().get("description", ""))[:200]
        except ValueError:
            description = ""
        retryable = response.status_code == 429 or response.status_code >= 500
        raise NotificationDeliveryError(
            f"Telegram respondió {response.status_code}: {description}".strip(), retryable=retryable
        )

    async def check(self) -> tuple[bool, str]:
        """Llama a getMe para comprobar el token (lo usa el health de integraciones)."""
        if not self._bot_token:
            return False, "TELEGRAM_BOT_TOKEN no configurado"
        try:
            response = await self._client.get(f"{self._api_base}/bot{self._bot_token}/getMe")
            if response.status_code == 200 and response.json().get("ok"):
                username = response.json().get("result", {}).get("username", "")
                return True, f"Bot @{username} operativo"
            return False, f"Telegram respondió {response.status_code}"
        except (httpx.HTTPError, ValueError) as error:
            return False, f"Sin conexión con Telegram ({type(error).__name__})"
