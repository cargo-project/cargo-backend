"""Entorno de Alembic (engine async, metadata de los modelos ORM de todos los módulos)."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config.settings import get_settings
from app.infrastructure.database.model_registry import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# PostGIS trae sus propias tablas (spatial_ref_sys) que no son parte de nuestro modelo.
_EXTERNAL_TABLES = {"spatial_ref_sys"}


def _include_object(obj: object, name: str | None, type_: str, reflected: bool, compare_to: object) -> bool:
    if type_ == "table" and (name in _EXTERNAL_TABLES or (reflected and compare_to is None)):
        # Las tablas que crean las extensiones de PostGIS (tiger, topology...) no las tocamos.
        return False
    return bool(alembic_helpers.include_object(obj, name, type_, reflected, compare_to))


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=metadata,
        include_object=_include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
        compare_type=True,
    )


def run_migrations_offline() -> None:
    _configure(url=get_settings().database_url)
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
