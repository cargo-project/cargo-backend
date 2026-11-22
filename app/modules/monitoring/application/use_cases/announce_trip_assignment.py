from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger("cargo.ingestion")

_COORDINATE_KEYS = ("origin_latitude", "origin_longitude", "destination_latitude", "destination_longitude")


class DeviceDirectory(Protocol):
    async def code_of(self, device_id: uuid.UUID) -> str | None: ...


class EdgeAssignmentPublisher(Protocol):
    """Le entrega el viaje activo al dispositivo (mensaje retenido en el broker IoT)."""

    async def publish(self, device_code: str, assignment: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class TripLifecycleNotice:
    trip_id: str
    trip_code: str | None
    device_id: uuid.UUID | None
    active: bool
    details: dict[str, Any]


class AnnounceTripAssignmentUseCase:
    """Le dice al gateway del vehículo con qué viaje tiene que marcar su telemetría.

    Se dispara con trip/started (activo) y trip/ended (inactivo). El dispositivo se queda
    con la asignación retenida, así sabe su viaje aunque se reconecte.
    """

    def __init__(self, devices: DeviceDirectory, publisher: EdgeAssignmentPublisher) -> None:
        self._devices = devices
        self._publisher = publisher

    async def execute(self, notice: TripLifecycleNotice) -> bool:
        if notice.device_id is None:
            return False
        device_code = await self._devices.code_of(notice.device_id)
        if device_code is None:
            logger.warning("trip assignment for unknown device", extra={"device_id": str(notice.device_id)})
            return False
        assignment: dict[str, Any] = {"trip_id": notice.trip_id, "trip_code": notice.trip_code, "active": notice.active}
        if notice.active:
            assignment.update({key: notice.details.get(key) for key in _COORDINATE_KEYS})
        await self._publisher.publish(device_code, assignment)
        logger.info("trip assignment announced to edge", extra={"device": device_code, "active": notice.active})
        return True
