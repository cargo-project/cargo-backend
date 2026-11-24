"""Telegram obligatorio en las cuentas y recuperación de contraseña con código por Telegram."""

from __future__ import annotations

import pytest

from tests.api.conftest import ApiClient
from tests.support.fake_messenger import FakeMessenger
from tests.support.seed import ADMIN_EMAIL, PASSWORD

pytestmark = pytest.mark.integration

NEW_PASSWORD = "Nueva-Frase-Segura-2026"


def _new_user(chat_id: str | None) -> dict[str, object]:
    body: dict[str, object] = {
        "email": "nuevo@cargo.test",
        "fullName": "Nuevo Usuario",
        "password": "Frase-Segura-Nueva-1",
        "role": "OPERATOR",
    }
    if chat_id is not None:
        body["telegramChatId"] = chat_id
    return body


async def test_new_accounts_require_a_reachable_telegram(admin: ApiClient, messenger: FakeMessenger) -> None:
    assert (await admin.post("/api/v1/users", json=_new_user(None))).status_code == 422

    messenger.unreachable.add("555")
    unreachable = await admin.post("/api/v1/users", json=_new_user("555"))
    assert unreachable.status_code == 422
    assert unreachable.json()["error"]["code"] == "telegram_unreachable"

    created = await admin.post("/api/v1/users", json=_new_user("777"))
    assert created.status_code == 201, created.text
    assert created.json()["data"]["telegramChatId"] == "777"
    assert messenger.sent[-1][0] == "777" and "vinculada" in messenger.sent[-1][1]


async def test_password_reset_with_telegram_code(client: ApiClient, admin: ApiClient, messenger: FakeMessenger) -> None:
    await admin.post("/api/v1/auth/logout")
    requested = await client.post("/api/v1/auth/password-reset/request", json={"email": ADMIN_EMAIL})
    assert requested.status_code == 202
    assert messenger.sent[-1][0] == "900001"  # el chat de Telegram de la cuenta admin
    code = messenger.last_code()

    wrong = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"email": ADMIN_EMAIL, "code": "000000" if code != "000000" else "111111", "newPassword": NEW_PASSWORD},
    )
    assert wrong.status_code == 422
    assert wrong.json()["error"]["code"] == "invalid_reset_code"

    weak = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"email": ADMIN_EMAIL, "code": code, "newPassword": "corta-123"}
    )
    assert weak.status_code == 422  # la política de contraseñas también aplica (y el código sigue vigente)

    confirmed = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"email": ADMIN_EMAIL, "code": code, "newPassword": NEW_PASSWORD}
    )
    assert confirmed.status_code == 204, confirmed.text
    assert "cambió correctamente" in messenger.sent[-1][1]

    reused = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"email": ADMIN_EMAIL, "code": code, "newPassword": NEW_PASSWORD}
    )
    assert reused.status_code == 422  # un solo uso
    assert (await client.login(password=PASSWORD)).status_code == 401
    assert (await client.login(password=NEW_PASSWORD)).status_code == 200


async def test_reset_request_never_reveals_accounts(
    client: ApiClient, admin: ApiClient, messenger: FakeMessenger
) -> None:
    known = await client.post("/api/v1/auth/password-reset/request", json={"email": ADMIN_EMAIL})
    unknown = await client.post("/api/v1/auth/password-reset/request", json={"email": "nadie@cargo.test"})
    invalid = await client.post("/api/v1/auth/password-reset/request", json={"email": "no-es-correo"})
    assert known.status_code == unknown.status_code == invalid.status_code == 202
    assert known.json() == unknown.json() == invalid.json()
    assert len(messenger.sent) == 1  # solo la cuenta real recibe el código


async def test_reset_codes_are_rate_limited_and_attempt_limited(
    client: ApiClient, admin: ApiClient, messenger: FakeMessenger
) -> None:
    for _ in range(4):
        await client.post("/api/v1/auth/password-reset/request", json={"email": ADMIN_EMAIL})
    assert len(messenger.sent) == 3  # máximo 3 códigos cada 15 minutos
    code = messenger.last_code()
    other = "123456" if code != "123456" else "654321"
    for _ in range(5):
        await client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"email": ADMIN_EMAIL, "code": other, "newPassword": NEW_PASSWORD},
        )
    blocked = await client.post(
        "/api/v1/auth/password-reset/confirm", json={"email": ADMIN_EMAIL, "code": code, "newPassword": NEW_PASSWORD}
    )
    assert blocked.status_code == 422  # tras 5 intentos fallidos el código deja de servir
