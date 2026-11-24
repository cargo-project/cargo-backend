from __future__ import annotations

import pytest

from tests.api.conftest import ApiClient
from tests.support.seed import ADMIN_EMAIL, PASSWORD

pytestmark = pytest.mark.integration


async def test_login_sets_secure_cookies_and_returns_user(client: ApiClient) -> None:
    response = await client.login()
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["email"] == ADMIN_EMAIL and body["role"] == "ADMIN" and body["fullName"] == "Admin CarGO"
    cookies = response.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("cargo_access="))
    refresh = next(c for c in cookies if c.startswith("cargo_refresh="))
    csrf = next(c for c in cookies if c.startswith("cargo_csrf="))
    assert "HttpOnly" in access and "HttpOnly" in refresh
    assert "HttpOnly" not in csrf  # el frontend la tiene que poder leer
    assert "SameSite=strict" in refresh.replace("Strict", "strict")
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_me_requires_session(client: ApiClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "invalid_session" and error["requestId"]


async def test_wrong_password_uses_generic_error(client: ApiClient) -> None:
    response = await client.login(password="incorrecta-123")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    unknown = await client.login(email="nadie@cargo.test")
    assert unknown.json()["error"]["message"] == response.json()["error"]["message"]


async def test_state_changing_request_without_csrf_header_is_forbidden(admin: ApiClient) -> None:
    response = await admin.post(
        "/api/v1/notification-recipients",
        json={"name": "Ana", "telegramChatId": "1"},
        headers={"X-CSRF-Token": "forged"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


async def test_refresh_rotates_session_and_logout_revokes(admin: ApiClient) -> None:
    old_refresh = admin.cookies["cargo_refresh"]
    refreshed = await admin.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert admin.cookies["cargo_refresh"] != old_refresh
    assert (await admin.post("/api/v1/auth/logout")).status_code == 204
    assert (await admin.get("/api/v1/auth/me")).status_code == 401


async def test_change_password_revokes_sessions(admin: ApiClient) -> None:
    weak = await admin.post("/api/v1/auth/change-password", json={"currentPassword": PASSWORD, "newPassword": "corta"})
    assert weak.status_code == 422
    changed = await admin.post(
        "/api/v1/auth/change-password", json={"currentPassword": PASSWORD, "newPassword": "Otra-Frase-Segura-99"}
    )
    assert changed.status_code == 204
    assert (await admin.login(password="Otra-Frase-Segura-99")).status_code == 200


async def test_operator_cannot_change_settings_or_administer(operator: ApiClient) -> None:
    settings = (await operator.get("/api/v1/settings")).json()["data"]
    response = await operator.put("/api/v1/settings", json=settings)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert (await operator.get("/api/v1/users")).status_code == 403
    assert (await operator.get("/api/v1/integration-health")).status_code == 403
    assert (await operator.get("/api/v1/admin/overview")).status_code == 403
    assert (await operator.get("/api/v1/admin/activity")).status_code == 403


async def test_operator_manages_telegram_recipients(operator: ApiClient) -> None:
    created = await operator.post("/api/v1/notification-recipients", json={"name": "Ana", "telegramChatId": "1"})
    assert created.status_code == 201
    recipient_id = created.json()["data"]["id"]
    assert (await operator.delete(f"/api/v1/notification-recipients/{recipient_id}")).status_code == 204
