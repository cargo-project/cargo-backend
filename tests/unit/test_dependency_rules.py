"""Reglas de arquitectura que se ejecutan (dirección de dependencias de Clean Architecture).

* domain      -> solo puede importar la librería estándar, app.shared.domain y el dominio de su propio módulo.
* application -> no puede importar presentación, infraestructura ni frameworks concretos.
* Ningún módulo importa la infraestructura de otro (los contextos colaboran por puertos).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
FORBIDDEN_IN_DOMAIN = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "geoalchemy2",
    "asyncpg",
    "aiomqtt",
    "paho",
    "httpx",
    "jwt",
    "argon2",
    "pydantic",
    "app.infrastructure",
    "app.core",
    "app.composition",
    "app.entrypoints",
    "app.shared.application",
)
FORBIDDEN_IN_APPLICATION = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "geoalchemy2",
    "asyncpg",
    "aiomqtt",
    "paho",
    "httpx",
    "jwt",
    "argon2",
    "app.infrastructure",
    "app.composition",
    "app.entrypoints",
    "app.core",
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _layer_files(layer: str) -> list[Path]:
    return sorted(p for p in APP.glob(f"modules/*/{layer}/**/*.py")) + (
        sorted(APP.glob(f"shared/{layer}/**/*.py")) if layer in ("domain", "application") else []
    )


def _module_of(path: Path) -> str | None:
    parts = path.relative_to(APP).parts
    return parts[1] if parts[0] == "modules" else None


@pytest.mark.parametrize("path", _layer_files("domain"), ids=lambda p: str(p.relative_to(APP)))
def test_domain_is_framework_free(path: Path) -> None:
    module = _module_of(path)
    for name in _imports(path):
        assert not name.startswith(FORBIDDEN_IN_DOMAIN), f"{path.name} imports {name}"
        if name.startswith("app.modules.") and module is not None:
            assert name.startswith(f"app.modules.{module}.domain"), f"{path.name} imports {name}"
        assert ".presentation" not in name and ".application" not in name, f"{path.name} imports {name}"


@pytest.mark.parametrize("path", _layer_files("application"), ids=lambda p: str(p.relative_to(APP)))
def test_application_depends_only_inwards(path: Path) -> None:
    for name in _imports(path):
        assert not name.startswith(FORBIDDEN_IN_APPLICATION), f"{path.name} imports {name}"
        assert ".presentation" not in name and ".infrastructure" not in name, f"{path.name} imports {name}"


def test_modules_never_import_foreign_infrastructure() -> None:
    for path in APP.glob("modules/*/**/*.py"):
        module = _module_of(path)
        for name in _imports(path):
            if name.startswith("app.modules.") and ".infrastructure" in name:
                assert name.startswith(f"app.modules.{module}."), f"{path} imports {name}"


def test_routers_do_not_touch_persistence_or_messaging() -> None:
    for path in APP.glob("modules/*/presentation/**/*.py"):
        for name in _imports(path):
            # Presentación llega a los adaptadores solo por la raíz de composición (inyección de dependencias).
            assert not name.startswith(("sqlalchemy", "aiomqtt", "httpx", "app.infrastructure")), (
                f"{path.name} imports {name}"
            )
