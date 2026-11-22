"""Datos de prueba para desarrollo (idempotente), cargados con los mismos casos de uso de la app.

Uso (Docker):  docker compose run --rm api python -m scripts.seed_dev_data
Uso (local):   python -m scripts.seed_dev_data
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from app.composition import fleet_factory, identity_factory, notifications_factory, trips_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.core.config.settings import get_settings
from app.core.logging.logging_config import configure_logging
from app.modules.fleet.application.dto.fleet_dto import DeviceData, DriverData, VehicleData
from app.modules.identity.application.dto.identity_dto import CreateUserCommand
from app.shared.domain.errors import ConflictError
from app.shared.domain.geo_point import GeoPoint

logger = logging.getLogger("cargo.seed")
SYSTEM_ACTOR = None

VEHICLES = [
    VehicleData("TRK-003", "ABC-123", "Volvo", "FH16", "Tracto con semirremolque", "available"),
    VehicleData("TRK-011", "BCD-456", "Scania", "R450", "Cisterna", "available"),
    VehicleData("TRK-018", "CDE-789", "Mercedes-Benz", "Actros", "Plataforma", "maintenance"),
]
DRIVERS = [
    DriverData("Carlos", "Mendoza", "45128796", "Q45128796", "987654321", "available", "DRV-001"),
    DriverData("Lucía", "Paredes", "70451236", "Q70451236", "912345678", "available", "DRV-002"),
    DriverData("Jorge", "Salas", "41236587", "Q41236587", "955443322", "inactive", "DRV-003"),
]
DEVICES = [
    DeviceData("DEV-GW-003", "edge_gateway", "EGW-PE-90231", "2.4.1", True, "TRK-003"),
    DeviceData("DEV-GW-011", "edge_gateway", "EGW-PE-90232", "2.4.1", True, "TRK-011"),
    DeviceData("DEV-GNSS-029", "gnss", "GNS-88501", "1.9.0", False, None),
]
LURIN_DEPOT = [
    GeoPoint(-12.2700, -76.8800),
    GeoPoint(-12.2700, -76.8600),
    GeoPoint(-12.2850, -76.8600),
    GeoPoint(-12.2850, -76.8800),
]


async def _ignore_existing(label: str, coroutine: object) -> None:
    try:
        await coroutine  # type: ignore[misc]
        logger.info("seeded", extra={"item": label})
    except ConflictError:
        logger.info("already present", extra={"item": label})
    except Exception as error:
        logger.warning("seed item skipped", extra={"item": label, "reason": str(error)})


async def seed(resources: AppResources) -> None:
    accounts = [
        (
            os.environ.get("SEED_ADMIN_EMAIL", "admin@cargo.local"),
            "Administrador CarGO",
            "ADMIN",
            os.environ.get("SEED_ADMIN_PASSWORD", ""),
        ),
        (
            os.environ.get("SEED_OPERATOR_EMAIL", "operador@cargo.local"),
            "Operador de Turno",
            "OPERATOR",
            os.environ.get("SEED_OPERATOR_PASSWORD", ""),
        ),
    ]
    for email, name, role, password in accounts:
        if not password:
            logger.warning("password not set; user skipped", extra={"user": email})
            continue
        async with open_scope(resources) as scope:
            await _ignore_existing(
                email,
                identity_factory.create_user(scope).execute(
                    CreateUserCommand(email, name, password, role), actor_id=SYSTEM_ACTOR
                ),
            )
    actor = uuid.UUID(int=0)
    for vehicle in VEHICLES:
        async with open_scope(resources) as scope:
            await _ignore_existing(vehicle.code, fleet_factory.create_vehicle(scope).execute(vehicle, actor_id=actor))
    for driver in DRIVERS:
        async with open_scope(resources) as scope:
            await _ignore_existing(str(driver.code), fleet_factory.create_driver(scope).execute(driver, actor_id=actor))
    for device in DEVICES:
        async with open_scope(resources) as scope:
            await _ignore_existing(device.code, fleet_factory.register_device(scope).execute(device, actor_id=actor))
    async with open_scope(resources) as scope:
        await _ignore_existing(
            "recipient",
            notifications_factory.create_recipient(scope).execute(
                name="Centro de control",
                telegram_chat_id=os.environ.get("SEED_TELEGRAM_CHAT_ID", "100000001"),
                actor_id=actor,
            ),
        )
    async with open_scope(resources) as scope:
        await _ignore_existing(
            "ZONA-LURIN",
            trips_factory.create_geofence(scope).execute(
                code="ZONA-LURIN", name="Depósito Lurín", boundary=LURIN_DEPOT, actor_id=actor
            ),
        )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    resources = AppResources.build(settings)
    try:
        await seed(resources)
    finally:
        await resources.aclose()


if __name__ == "__main__":
    asyncio.run(main())
