"""Fixtures de pytest que comparten los tests de integración y de API (se importan desde sus conftest)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.composition.resources import AppResources
from app.core.config.settings import Settings
from tests.support.database import build_test_settings, prepare_database, truncate_all


@pytest.fixture(scope="session")
def database_url() -> str:
    return prepare_database()


@pytest.fixture(scope="session")
def settings(database_url: str) -> Settings:
    return build_test_settings(database_url)


@pytest.fixture
async def resources(settings: Settings) -> AsyncIterator[AppResources]:
    resources = AppResources.build(settings)
    await truncate_all(resources.engine)
    try:
        yield resources
    finally:
        await resources.aclose()
