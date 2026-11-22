from __future__ import annotations

import uuid
from datetime import UTC, datetime

from geoalchemy2.elements import WKBElement, WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import delete, exists, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.modules.trips.domain.entities.trip import Trip
from app.modules.trips.domain.exceptions.trip_errors import InvalidTripStateError
from app.modules.trips.domain.value_objects.location import Location
from app.modules.trips.domain.value_objects.monitoring_configuration import MonitoringConfiguration
from app.modules.trips.domain.value_objects.trip_status import TripStatus
from app.modules.trips.infrastructure.persistence.trip_models import (
    TripModel,
    trip_notification_recipients,
)
from app.shared.domain.geo_point import GeoPoint

_UPSERT_DESTINATION_GEOFENCE = text(
    """
    INSERT INTO geofences (id, code, name, kind, trip_id, area, created_at)
    VALUES (:id, :code, :name, 'destination', :trip_id,
            ST_Buffer(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius, 'quad_segs=16')::geometry,
            :now)
    ON CONFLICT (trip_id) WHERE kind = 'destination'
    DO UPDATE SET area = EXCLUDED.area, name = EXCLUDED.name
    """
)


def _point_wkt(point: GeoPoint) -> WKTElement:
    return WKTElement(f"POINT({point.longitude} {point.latitude})", srid=4326)


def _geo_point(element: WKBElement | WKTElement) -> GeoPoint:
    shape = to_shape(element)
    return GeoPoint(latitude=shape.y, longitude=shape.x)


class PostgresTripRepository:
    """Guarda el agregado Trip en trips, trip_notification_recipients
    y su zona de llegada (geocerca de destino).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, trip_id: uuid.UUID) -> Trip | None:
        model = await self._session.get(TripModel, trip_id)
        return await self._to_domain(model) if model else None

    async def get_by_code(self, code: str) -> Trip | None:
        model = await self._session.scalar(select(TripModel).where(TripModel.code == code))
        return await self._to_domain(model) if model else None

    async def code_exists(self, code: str) -> bool:
        return bool(await self._session.scalar(select(exists().where(TripModel.code == code))))

    async def list_ongoing(self) -> list[Trip]:
        models = await self._session.scalars(select(TripModel).where(TripModel.status == TripStatus.ONGOING.value))
        return [await self._to_domain(model) for model in models]

    async def add(self, trip: Trip) -> None:
        model = TripModel(id=trip.id, version=1)
        self._copy(trip, model)
        self._session.add(model)
        # No hay relationship ORM entre estas tablas (el mapeo del agregado es explícito), así que
        # primero se hace flush del viaje para que pasen las FK de destinatarios y zona de llegada.
        await self._session.flush()
        await self._replace_recipients(trip)
        await self._upsert_destination_geofence(trip)

    async def save(self, trip: Trip) -> None:
        model = await self._session.get(TripModel, trip.id)
        if model is None:
            await self.add(trip)
            return
        radius_changed = (
            model.monitoring_configuration.get("arrival_radius_m") != trip.monitoring_configuration.arrival_radius_m
        )
        self._copy(trip, model)
        try:
            await self._session.flush()
        except StaleDataError as error:
            raise InvalidTripStateError(
                f"El viaje {trip.code} fue modificado por otra operación; vuelve a intentarlo."
            ) from error
        if radius_changed:
            await self._upsert_destination_geofence(trip)

    # ------------------------------------------------------------------ mapeo
    @staticmethod
    def _copy(trip: Trip, model: TripModel) -> None:
        model.code = trip.code
        model.vehicle_id = trip.vehicle_id
        model.driver_id = trip.driver_id
        model.device_id = trip.device_id
        model.client_id = trip.client_id
        model.origin_label = trip.origin.label
        model.origin = _point_wkt(trip.origin.point)
        model.destination_label = trip.destination.label
        model.destination = _point_wkt(trip.destination.point)
        model.cargo_description = trip.cargo_description
        model.status = trip.status.value
        model.monitoring_configuration = trip.monitoring_configuration.as_dict()
        model.planned_start_at = trip.planned_start_at
        model.started_at = trip.started_at
        model.completed_at = trip.completed_at
        model.cancelled_at = trip.cancelled_at
        model.end_reason = trip.end_reason
        model.created_at = trip.created_at
        model.created_by = trip.created_by

    async def _to_domain(self, model: TripModel) -> Trip:
        recipient_ids = await self._session.scalars(
            select(trip_notification_recipients.c.recipient_id).where(
                trip_notification_recipients.c.trip_id == model.id
            )
        )
        return Trip(
            id=model.id,
            code=model.code,
            vehicle_id=model.vehicle_id,
            driver_id=model.driver_id,
            origin=Location(model.origin_label, _geo_point(model.origin)),
            destination=Location(model.destination_label, _geo_point(model.destination)),
            cargo_description=model.cargo_description,
            monitoring_configuration=MonitoringConfiguration.from_stored(model.monitoring_configuration),
            recipient_ids=frozenset(recipient_ids),
            status=TripStatus(model.status),
            created_at=model.created_at,
            created_by=model.created_by,
            client_id=model.client_id,
            planned_start_at=model.planned_start_at,
            device_id=model.device_id,
            started_at=model.started_at,
            completed_at=model.completed_at,
            cancelled_at=model.cancelled_at,
            end_reason=model.end_reason,
        )

    async def _replace_recipients(self, trip: Trip) -> None:
        await self._session.execute(
            delete(trip_notification_recipients).where(trip_notification_recipients.c.trip_id == trip.id)
        )
        if trip.recipient_ids:
            await self._session.execute(
                insert(trip_notification_recipients),
                [{"trip_id": trip.id, "recipient_id": rid} for rid in trip.recipient_ids],
            )

    async def _upsert_destination_geofence(self, trip: Trip) -> None:
        await self._session.execute(
            _UPSERT_DESTINATION_GEOFENCE,
            {
                "id": uuid.uuid4(),
                "code": f"DEST-{trip.code}",
                "name": f"Destino {trip.code}",
                "trip_id": trip.id,
                "lon": trip.destination.point.longitude,
                "lat": trip.destination.point.latitude,
                "radius": float(trip.monitoring_configuration.arrival_radius_m),
                "now": datetime.now(UTC),
            },
        )
