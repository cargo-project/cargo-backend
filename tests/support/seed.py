"""Ayudas para crear datos realistas usando los mismos casos de uso de la app."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.composition import fleet_factory, identity_factory, notifications_factory, trips_factory
from app.composition.resources import AppResources
from app.composition.scope import open_scope
from app.modules.fleet.application.dto.fleet_dto import DeviceData, DriverData, VehicleData
from app.modules.identity.application.dto.identity_dto import CreateUserCommand
from app.modules.trips.application.dto.trip_dto import CreateTripCommand

ADMIN_EMAIL = "admin@cargo.test"
OPERATOR_EMAIL = "operador@cargo.test"
PASSWORD = "Contrasena-Segura-2026"

LIMA = (-12.0464, -77.0428)
ICA = (-14.0678, -75.7286)


@dataclass
class SeededFleet:
    vehicle_code: str
    driver_code: str
    device_code: str
    recipient_id: uuid.UUID


async def seed_users(resources: AppResources) -> None:
    async with open_scope(resources) as scope:
        create = identity_factory.create_user(scope)
        await create.execute(CreateUserCommand(ADMIN_EMAIL, "Admin CarGO", PASSWORD, "ADMIN"), actor_id=None)
    async with open_scope(resources) as scope:
        create = identity_factory.create_user(scope)
        await create.execute(CreateUserCommand(OPERATOR_EMAIL, "Operador CarGO", PASSWORD, "OPERATOR"), actor_id=None)


async def seed_fleet(resources: AppResources, suffix: str = "001") -> SeededFleet:
    actor = uuid.uuid4()
    async with open_scope(resources) as scope:
        await fleet_factory.create_vehicle(scope).execute(
            VehicleData(f"TRK-{suffix}", f"ABC-{suffix}", "Volvo", "FH16", "Tracto", "available"), actor_id=actor
        )
    async with open_scope(resources) as scope:
        driver = await fleet_factory.create_driver(scope).execute(
            DriverData("Ana", "Quispe", f"70{suffix}123", f"Q70{suffix}123", "999888777", "available"), actor_id=actor
        )
    async with open_scope(resources) as scope:
        await fleet_factory.register_device(scope).execute(
            DeviceData(f"DEV-GW-{suffix}", "edge_gateway", f"EGW-{suffix}", "2.0.0", True, f"TRK-{suffix}"),
            actor_id=actor,
        )
    async with open_scope(resources) as scope:
        recipient = await notifications_factory.create_recipient(scope).execute(
            name=f"Supervisor {suffix}", telegram_chat_id=f"10{suffix}", actor_id=actor
        )
    return SeededFleet(f"TRK-{suffix}", driver.code, f"DEV-GW-{suffix}", recipient.id)


async def create_actor(resources: AppResources) -> uuid.UUID:
    async with open_scope(resources) as scope:
        user = await identity_factory.create_user(scope).execute(
            CreateUserCommand(f"actor-{uuid.uuid4().hex[:8]}@cargo.test", "Planificador", PASSWORD, "OPERATOR"),
            actor_id=None,
        )
    return user.id


async def create_trip(resources: AppResources, fleet: SeededFleet) -> str:
    actor = await create_actor(resources)
    async with open_scope(resources) as scope:
        return await trips_factory.create_trip(scope).execute(
            CreateTripCommand(
                vehicle_code=fleet.vehicle_code,
                driver_code=fleet.driver_code,
                origin_label="Lima",
                origin_latitude=LIMA[0],
                origin_longitude=LIMA[1],
                destination_label="Ica",
                destination_latitude=ICA[0],
                destination_longitude=ICA[1],
                cargo_description="Cemento 30 t",
                recipient_ids=frozenset({fleet.recipient_id}),
            ),
            actor_id=actor,
        )


async def start_trip(resources: AppResources, code: str) -> None:
    async with open_scope(resources) as scope:
        await trips_factory.start_trip(scope).execute(code, actor_id=None)
