"""Ciclo de vida de la BD de pruebas: una base aparte migrada con Alembic (nunca create_all)."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_URL = "postgresql+asyncpg://cargo:cargo@127.0.0.1:55432/cargo_test"
PRESERVED_TABLES = {"alembic_version", "spatial_ref_sys", "monitoring_defaults", "system_settings"}


def database_url_from_env() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_URL)


async def _recreate_database(url: str) -> None:
    parsed = urlparse(url.replace("+asyncpg", ""))
    name = parsed.path.lstrip("/")
    admin_dsn = parsed._replace(path="/postgres").geturl()
    connection = await asyncpg.connect(admin_dsn, timeout=5)
    try:
        await connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()


def prepare_database() -> str:
    url = database_url_from_env()
    try:
        asyncio.run(_recreate_database(url))
    except (OSError, asyncpg.PostgresError, TimeoutError) as error:
        pytest.skip(f"PostgreSQL/PostGIS not reachable for integration tests: {error}")
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    return url


def build_test_settings(database_url: str) -> Settings:
    return Settings(
        environment="test",
        database_url=database_url,
        database_pool_size=5,
        run_background_workers=False,
        cookie_secure=False,
        cors_origins=["http://localhost:3000"],
        mapbox_token=None,
        telegram_bot_token=None,
        mqtt_internal_host=os.environ.get("TEST_MQTT_HOST", "127.0.0.1"),
        mqtt_internal_port=int(os.environ.get("TEST_MQTT_PORT", "51883")),
    )


async def truncate_all(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        tables = (
            (await connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")))
            .scalars()
            .all()
        )
        targets = [f'"{t}"' for t in tables if t not in PRESERVED_TABLES]
        if targets:
            await connection.execute(text(f"TRUNCATE {', '.join(targets)} CASCADE"))
