"""Registro desde el login (pendiente de aprobación), perfil propio y lista de integraciones."""

from __future__ import annotations

import pytest

from tests.api.conftest import ApiClient
from tests.support.fake_messenger import FakeMessenger

pytestmark = pytest.mark.integration

SIGN_UP = {
    "email": "postulante@cargo.test",
    "fullName": "Rosa Postulante",
    "password": "Mi-Frase-Segura-2026",
    "telegramChatId": "424242",
}


async def test_self_sign_up_waits_for_admin_approval(
    client: ApiClient, admin: ApiClient, messenger: FakeMessenger
) -> None:
    await admin.post("/api/v1/auth/logout")
    created = await client.post("/api/v1/auth/register", json=SIGN_UP)
    assert created.status_code == 201, created.text
    assert messenger.sent[-1][0] == "424242" and "solicitud" in messenger.sent[-1][1]
    assert (await client.post("/api/v1/auth/register", json=SIGN_UP)).status_code == 409

    pending = await client.login(email=SIGN_UP["email"], password=SIGN_UP["password"])
    assert pending.status_code == 403
    assert pending.json()["error"]["code"] == "account_pending_approval"
    wrong = await client.login(email=SIGN_UP["email"], password="otra-clave-cualquiera")
    assert wrong.status_code == 401  # sin la contraseña correcta no se revela nada

    await client.login()  # vuelve a entrar como admin
    account = next(
        a
        for a in (await client.get("/api/v1/admin/overview")).json()["data"]["accounts"]
        if a["email"] == SIGN_UP["email"]
    )
    assert account["role"] == "OPERATOR" and account["isActive"] is False and account["lastLoginAt"] is None
    approved = await client.patch(f"/api/v1/users/{account['id']}", json={"isActive": True})
    assert approved.status_code == 200
    assert messenger.sent[-1][0] == "424242" and "ya está activa" in messenger.sent[-1][1]
    await client.post("/api/v1/auth/logout")
    assert (await client.login(email=SIGN_UP["email"], password=SIGN_UP["password"])).status_code == 200


async def test_sign_up_requires_a_reachable_telegram(client: ApiClient, messenger: FakeMessenger) -> None:
    without = {k: v for k, v in SIGN_UP.items() if k != "telegramChatId"}
    assert (await client.post("/api/v1/auth/register", json=without)).status_code == 422
    messenger.unreachable.add("999")
    unreachable = await client.post("/api/v1/auth/register", json={**SIGN_UP, "telegramChatId": "999"})
    assert unreachable.status_code == 422
    assert unreachable.json()["error"]["code"] == "telegram_unreachable"


async def test_operator_updates_own_profile(operator: ApiClient, messenger: FakeMessenger) -> None:
    updated = await operator.patch("/api/v1/auth/me", json={"fullName": "Operadora Norte", "telegramChatId": "313131"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["fullName"] == "Operadora Norte"
    assert updated.json()["data"]["telegramChatId"] == "313131"
    assert messenger.sent[-1][0] == "313131" and "vinculada" in messenger.sent[-1][1]
    assert (await operator.patch("/api/v1/auth/me", json={"telegramChatId": ""})).status_code == 422
    assert (await operator.get("/api/v1/auth/me")).json()["data"]["role"] == "OPERATOR"  # no puede cambiar su rol


async def test_integrations_no_longer_list_mapbox(admin: ApiClient) -> None:
    keys = {item["key"] for item in (await admin.get("/api/v1/integration-health")).json()["data"]}
    assert "mapbox" not in keys and {"database", "cep", "telegram"} <= keys
