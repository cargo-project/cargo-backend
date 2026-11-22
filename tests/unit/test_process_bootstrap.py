"""Regresión: los procesos sueltos tienen que cargar la metadata ORM completa.

Se encontró en la prueba de punta a punta: el proceso de ingesta no importaba los modelos
de viajes, y al hacer flush de un TelemetryEvent fallaba con NoReferencedTableError.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "entrypoint",
    ["app.entrypoints.ingestion_service", "app.entrypoints.geospatial_service", "app.entrypoints.notification_service"],
)
def test_entrypoint_registers_every_table(entrypoint: str) -> None:
    code = (
        f"import {entrypoint}\n"
        "from sqlalchemy.orm import configure_mappers\n"
        "from app.infrastructure.database.base import Base\n"
        "configure_mappers()\n"
        "for table in Base.metadata.tables.values():\n"
        "    for fk in table.foreign_keys:\n"
        "        fk.column  # raises NoReferencedTableError if a referenced table is missing\n"
        "print(len(Base.metadata.tables))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) >= 20
