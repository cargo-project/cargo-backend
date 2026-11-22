"""Prueba segura de Telegram usando el mismo adaptador de producción.

1. Llama a getMe para validar TELEGRAM_BOT_TOKEN (no manda nada).
2. Solo si se pasa --send Y está TELEGRAM_TEST_CHAT_ID, manda un mensaje de prueba.

    docker compose exec api python -m scripts.telegram_check
    docker compose exec api python -m scripts.telegram_check --send
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import httpx

from app.core.config.settings import get_settings
from app.infrastructure.telegram.telegram_notification_adapter import TelegramNotificationAdapter
from app.modules.notifications.domain.exceptions.notification_errors import NotificationDeliveryError


async def run(send: bool) -> int:
    settings = get_settings()
    token = settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else None
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        adapter = TelegramNotificationAdapter(client, token, settings.telegram_api_base)
        ok, detail = await adapter.check()
        print(f"getMe: {'OK' if ok else 'FAILED'} - {detail}")  # noqa: T201
        if not ok or not send:
            return 0 if ok else 1
        chat_id = os.environ.get("TELEGRAM_TEST_CHAT_ID", "")
        if not chat_id:
            print("TELEGRAM_TEST_CHAT_ID is empty: nothing sent.")  # noqa: T201
            return 1
        try:
            await adapter.send(chat_id, "CarGO: mensaje de prueba de configuración.")
        except NotificationDeliveryError as error:
            print(f"sendMessage FAILED: {error}")  # noqa: T201
            return 1
        print("sendMessage: OK")  # noqa: T201
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="also send one message to TELEGRAM_TEST_CHAT_ID")
    return asyncio.run(run(parser.parse_args().send))


if __name__ == "__main__":
    sys.exit(main())
