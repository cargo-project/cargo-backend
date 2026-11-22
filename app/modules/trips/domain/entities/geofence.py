from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.modules.trips.domain.exceptions.trip_errors import InvalidGeofenceError
from app.shared.domain.entity import Entity
from app.shared.domain.geo_point import GeoPoint

_CODE = re.compile(r"^[A-Z0-9-]{2,40}$")


class GeofenceKind(StrEnum):
    DESTINATION = "destination"  # sale del destino del viaje + radio de llegada
    ZONE = "zone"  # zona que define el operador (depósito, zona restringida, peaje...)


@dataclass(eq=False)
class Geofence(Entity):
    """Polígono definido por el operador para marcar en qué zona está cada lectura.

    Las zonas de llegada no se crean con esta entidad: salen del destino y del radio de
    llegada de cada viaje cuando se guarda el viaje.
    """

    id: uuid.UUID
    code: str
    name: str
    kind: GeofenceKind
    boundary: tuple[GeoPoint, ...]
    created_at: datetime

    @classmethod
    def define_zone(cls, *, code: str, name: str, boundary: list[GeoPoint], now: datetime) -> Geofence:
        normalised = code.strip().upper()
        if not _CODE.match(normalised):
            raise InvalidGeofenceError("Código de geocerca inválido.")
        ring = list(boundary)
        if len(ring) >= 2 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) < 3:
            raise InvalidGeofenceError("Una geocerca necesita al menos tres vértices distintos.")
        return cls(
            id=uuid.uuid4(),
            code=normalised,
            name=" ".join(name.split())[:120],
            kind=GeofenceKind.ZONE,
            boundary=tuple(ring),
            created_at=now,
        )

    def closed_ring_lon_lat(self) -> list[tuple[float, float]]:
        ring = [point.as_lon_lat() for point in self.boundary]
        return [*ring, ring[0]]
