from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.composition.resources import AppResources
from app.core.config.settings import Settings
from app.main import create_app
from tests.support.database import truncate_all
from tests.support.db_fixtures import database_url, settings
from tests.support.seed import ADMIN_EMAIL, OPERATOR_EMAIL, PASSWORD, seed_users

__all__ = ["database_url", "settings"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/api" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.integration)


class ApiClient(httpx.AsyncClient):
    """Se porta como apiClient.ts: cookies + X-CSRF-Token copiado de cargo_csrf."""

    async def request(self, method: str, url: httpx.URL | str, **kwargs: object) -> httpx.Response:  # type: ignore[override]
        if method.upper() not in {"GET", "HEAD", "OPTIONS"} and "cargo_csrf" in self.cookies:
            headers = dict(kwargs.pop("headers", None) or {})  # type: ignore[call-overload]
            headers.setdefault("X-CSRF-Token", self.cookies["cargo_csrf"])
            kwargs["headers"] = headers
        return await super().request(method, url, **kwargs)  # type: ignore[arg-type]

    async def login(self, email: str = ADMIN_EMAIL, password: str = PASSWORD) -> httpx.Response:
        return await self.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        resources: AppResources = application.state.resources
        await truncate_all(resources.engine)
        await seed_users(resources)
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[ApiClient]:
    transport = httpx.ASGITransport(app=app)
    async with ApiClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture
async def admin(client: ApiClient) -> ApiClient:
    assert (await client.login()).status_code == 200
    return client


@pytest.fixture
async def operator(client: ApiClient) -> ApiClient:
    assert (await client.login(OPERATOR_EMAIL)).status_code == 200
    return client
