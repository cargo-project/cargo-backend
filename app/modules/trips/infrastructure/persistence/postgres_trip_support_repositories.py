"""Repositorios de las entidades chicas de viajes (clientes, zonas, umbrales por defecto)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.trips.domain.entities.client import Client
from app.modules.trips.domain.entities.geofence import Geofence, GeofenceKind
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration
from app.modules.trips.infrastructure.persistence.trip_models import (
    ClientModel,
    GeofenceModel,
    MonitoringDefaultsModel,
)
from app.shared.domain.geo_point import GeoPoint

_DEFAULTS_ROW_ID = 1


class PostgresClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(m: ClientModel) -> Client:
        return Client(id=m.id, name=m.name, tax_id=m.tax_id, contact_email=m.contact_email, created_at=m.created_at)

    async def get_by_id(self, client_id: uuid.UUID) -> Client | None:
        model = await self._session.get(ClientModel, client_id)
        return self._to_domain(model) if model else None

    async def list_all(self) -> list[Client]:
        return [self._to_domain(m) for m in await self._session.scalars(select(ClientModel).order_by(ClientModel.name))]

    async def add(self, client: Client) -> None:
        self._session.add(
            ClientModel(
                id=client.id,
                name=client.name,
                tax_id=client.tax_id,
                contact_email=client.contact_email,
                created_at=client.created_at,
            )
        )
        await self._session.flush()


class PostgresGeofenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def code_exists(self, code: str) -> bool:
        return bool(await self._session.scalar(select(exists().where(GeofenceModel.code == code))))

    async def list_zones(self) -> list[Geofence]:
        models = await self._session.scalars(
            select(GeofenceModel).where(GeofenceModel.kind == GeofenceKind.ZONE.value).order_by(GeofenceModel.code)
        )
        result: list[Geofence] = []
        for m in models:
            ring = list(to_shape(m.area).exterior.coords)[:-1]
            result.append(
                Geofence(
                    id=m.id,
                    code=m.code,
                    name=m.name,
                    kind=GeofenceKind(m.kind),
                    boundary=tuple(GeoPoint(latitude=lat, longitude=lon) for lon, lat in ring),
                    created_at=m.created_at,
                )
            )
        return result

    async def add(self, geofence: Geofence) -> None:
        ring = ", ".join(f"{lon} {lat}" for lon, lat in geofence.closed_ring_lon_lat())
        self._session.add(
            GeofenceModel(
                id=geofence.id,
                code=geofence.code,
                name=geofence.name,
                kind=geofence.kind.value,
                trip_id=None,
                area=WKTElement(f"POLYGON(({ring}))", srid=4326),
                created_at=geofence.created_at,
            )
        )
        await self._session.flush()


class PostgresMonitoringDefaultsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> MonitoringConfiguration:
        model = await self._session.get(MonitoringDefaultsModel, _DEFAULTS_ROW_ID)
        return MonitoringConfiguration.from_stored(model.configuration) if model else MonitoringConfiguration()

    async def save(self, configuration: MonitoringConfiguration) -> None:
        model = await self._session.get(MonitoringDefaultsModel, _DEFAULTS_ROW_ID)
        now = datetime.now(UTC)
        if model is None:
            self._session.add(
                MonitoringDefaultsModel(id=_DEFAULTS_ROW_ID, configuration=configuration.as_dict(), updated_at=now)
            )
        else:
            model.configuration = configuration.as_dict()
            model.updated_at = now
        await self._session.flush()
