from __future__ import annotations

import pytest

from tests.support.db_fixtures import database_url, resources, settings

__all__ = ["database_url", "resources", "settings"]

pytestmark = pytest.mark.integration


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.integration)
